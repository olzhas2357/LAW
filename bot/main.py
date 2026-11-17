import asyncio
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Settings, get_settings
from bot.db.repo import Repository
from bot.handlers import admin, feedback, inline, qa, start, topics
from bot.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from bot.keyboards import topics_keyboard
from bot.middlewares.language import LanguageMiddleware
from bot.middlewares.logging import SafeLoggingMiddleware
from bot.middlewares.throttle import ThrottleMiddleware
from bot.services.data_loader import LegalDataset, LegalRecord, load_dataset
from bot.services.llm import ChatProvider, EmbeddingProvider, create_providers
from bot.services.search import HybridSearch

logger = logging.getLogger(__name__)


def _dataset_path(base_path: Path, language: str) -> Path:
    if language == DEFAULT_LANGUAGE:
        return base_path
    return base_path.with_name(f"{base_path.stem}_{language}{base_path.suffix}")


def _load_datasets(base_path: Path) -> dict[str, LegalDataset]:
    datasets = {
        language: load_dataset(_dataset_path(base_path, language))
        for language in SUPPORTED_LANGUAGES
    }
    for language, dataset in datasets.items():
        if dataset.meta.get("language") != language:
            raise ValueError(f"Dataset {language} has unexpected language metadata")
    record_ids = {
        language: {record.id for record in dataset.records}
        for language, dataset in datasets.items()
    }
    if any(ids != record_ids[DEFAULT_LANGUAGE] for ids in record_ids.values()):
        raise ValueError("Localized datasets must contain the same record IDs")
    return datasets


def _make_locale(
    language: str,
    dataset: LegalDataset,
    search: HybridSearch,
) -> "RuntimeLocale":
    disclaimer = str(dataset.meta.get("disclaimer", "")).strip()
    disclaimer = disclaimer.split(".", 1)[0]
    for prefix in ("Ескерту:", "Disclaimer:", "Предупреждение:"):
        disclaimer = disclaimer.removeprefix(prefix).strip()
    if not disclaimer:
        disclaimer = "Жалпы ақпарат."
    records_by_topic = defaultdict(list)
    for record in dataset.records:
        records_by_topic[record.topic].append(record)
    return RuntimeLocale(
        language=language,
        dataset=dataset,
        search=search,
        disclaimer=disclaimer,
        records_by_id={record.id: record for record in dataset.records},
        records_by_topic=records_by_topic,
    )


@dataclass
class RuntimeLocale:
    language: str
    dataset: LegalDataset
    search: HybridSearch
    disclaimer: str
    records_by_id: dict[int, LegalRecord]
    records_by_topic: dict[str, list[LegalRecord]]


def configure_logging() -> None:
    standard = logging.StreamHandler(sys.stdout)
    standard.addFilter(lambda record: record.levelno < logging.ERROR)
    errors = logging.StreamHandler(sys.stderr)
    errors.setLevel(logging.ERROR)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[standard, errors],
    )


class Runtime:
    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        locales: dict[str, RuntimeLocale],
        embedding_provider: EmbeddingProvider | None,
        chat_provider: ChatProvider | None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.locales = locales
        self.embedding_provider = embedding_provider
        self.chat_provider = chat_provider
        self.topic_pages: dict[int, str] = {}
        self.feedback_pending: dict[int, int | None] = {}
        self.broadcast_pending: dict[int, str] = {}
        self.logger = logger

    @property
    def dataset(self) -> LegalDataset:
        return self.locales[DEFAULT_LANGUAGE].dataset

    @property
    def search(self) -> HybridSearch:
        return self.locales[DEFAULT_LANGUAGE].search

    @property
    def disclaimer(self) -> str:
        return self.locales[DEFAULT_LANGUAGE].disclaimer

    @property
    def records_by_id(self) -> dict:
        return self.locales[DEFAULT_LANGUAGE].records_by_id

    @property
    def records_by_topic(self) -> dict:
        return self.locales[DEFAULT_LANGUAGE].records_by_topic

    def for_language(self, language: str) -> "LocalizedRuntime":
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        return LocalizedRuntime(self, language)

    def topic_menu(self):
        return topics_keyboard(self.dataset.topics, 0, DEFAULT_LANGUAGE)

    async def reload(self) -> None:
        datasets = _load_datasets(self.settings.data_path)
        embedding_provider, chat_provider = create_providers(self.settings)
        locales = {}
        for language, dataset in datasets.items():
            search = HybridSearch(dataset, self.settings.cache_dir / language, embedding_provider)
            await search.build()
            locales[language] = _make_locale(language, dataset, search)
        self.locales = locales
        self.embedding_provider = embedding_provider
        self.chat_provider = chat_provider
        self.topic_pages.clear()


class LocalizedRuntime:
    def __init__(self, runtime: Runtime, language: str) -> None:
        self.runtime = runtime
        self.language = language

    def __getattr__(self, name: str):
        locale = self.runtime.locales[self.language]
        if name in {
            "dataset", "search", "disclaimer", "records_by_id", "records_by_topic",
        }:
            return getattr(locale, name)
        return getattr(self.runtime, name)

    def for_language(self, language: str) -> "LocalizedRuntime":
        return self.runtime.for_language(language)

    def topic_menu(self):
        return topics_keyboard(
            self.runtime.locales[self.language].dataset.topics,
            0,
            self.language,
        )

    async def reload(self) -> None:
        await self.runtime.reload()


async def create_runtime(settings: Settings | None = None) -> Runtime:
    settings = settings or get_settings()
    datasets = _load_datasets(settings.data_path)
    embedding_provider, chat_provider = create_providers(settings)
    locales = {}
    for language, dataset in datasets.items():
        search = HybridSearch(dataset, settings.cache_dir / language, embedding_provider)
        await search.build()
        locales[language] = _make_locale(language, dataset, search)
    repository = Repository(settings.database_path)
    await repository.initialize()
    await repository.prune_logs(settings.log_retention_days)
    return Runtime(settings, repository, locales, embedding_provider, chat_provider)


def create_dispatcher(runtime: Runtime) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher["runtime"] = runtime
    dispatcher["repository"] = runtime.repository
    throttle = ThrottleMiddleware(runtime.settings)
    language = LanguageMiddleware()
    dispatcher.message.middleware(throttle)
    dispatcher.callback_query.middleware(throttle)
    dispatcher.inline_query.middleware(throttle)
    dispatcher.message.middleware(SafeLoggingMiddleware())
    dispatcher.message.middleware(language)
    dispatcher.callback_query.middleware(language)
    dispatcher.inline_query.middleware(language)
    dispatcher.include_routers(start.router, admin.router, topics.router, feedback.router, qa.router, inline.router)
    return dispatcher


async def run_polling(runtime: Runtime) -> None:
    bot = Bot(
        runtime.settings.bot_token,
    )
    dispatcher = create_dispatcher(runtime)
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()


async def run_webhook(runtime: Runtime) -> None:
    if not runtime.settings.webhook_url:
        raise ValueError("WEBHOOK_URL is required in webhook mode")
    bot = Bot(
        runtime.settings.bot_token,
    )
    dispatcher = create_dispatcher(runtime)
    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=runtime.settings.webhook_secret or None,
    ).register(app, path=runtime.settings.webhook_path)
    setup_application(app, dispatcher, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, runtime.settings.host, runtime.settings.port)
    await site.start()
    webhook_url = runtime.settings.webhook_url.rstrip("/") + runtime.settings.webhook_path
    await bot.set_webhook(
        webhook_url,
        secret_token=runtime.settings.webhook_secret or None,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )
    logger.info("Webhook server listening on %s:%s", runtime.settings.host, runtime.settings.port)
    try:
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()
        await bot.session.close()


async def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required; copy .env.example to .env and configure it")
    runtime = await create_runtime(settings)
    if settings.webhook_url:
        await run_webhook(runtime)
    else:
        await run_polling(runtime)


if __name__ == "__main__":
    asyncio.run(main())
