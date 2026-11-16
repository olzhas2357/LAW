import asyncio
import logging
import sys
from collections import defaultdict

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Settings, get_settings
from bot.db.repo import Repository
from bot.handlers import admin, feedback, inline, qa, start, topics
from bot.keyboards import topics_keyboard
from bot.middlewares.logging import SafeLoggingMiddleware
from bot.middlewares.throttle import ThrottleMiddleware
from bot.services.data_loader import LegalDataset, load_dataset
from bot.services.llm import ChatProvider, EmbeddingProvider, create_providers
from bot.services.search import HybridSearch

logger = logging.getLogger(__name__)


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
        dataset: LegalDataset,
        search: HybridSearch,
        embedding_provider: EmbeddingProvider | None,
        chat_provider: ChatProvider | None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.dataset = dataset
        self.search = search
        self.embedding_provider = embedding_provider
        self.chat_provider = chat_provider
        disclaimer = str(dataset.meta.get("disclaimer", "")).strip()
        self.disclaimer = disclaimer.split(".", 1)[0].removeprefix("Ескерту:").strip()
        if not self.disclaimer:
            self.disclaimer = "Жалпы ақпарат."
        self.records_by_id = {record.id: record for record in dataset.records}
        self.records_by_topic = defaultdict(list)
        for record in dataset.records:
            self.records_by_topic[record.topic].append(record)
        self.topic_pages: dict[int, str] = {}
        self.feedback_pending: dict[int, int | None] = {}
        self.broadcast_pending: dict[int, str] = {}
        self.logger = logger

    def topic_menu(self):
        return topics_keyboard(self.dataset.topics, 0)

    async def reload(self) -> None:
        dataset = load_dataset(self.settings.data_path)
        embedding_provider, chat_provider = create_providers(self.settings)
        search = HybridSearch(dataset, self.settings.cache_dir, embedding_provider)
        await search.build()
        self.dataset = dataset
        self.search = search
        self.embedding_provider = embedding_provider
        self.chat_provider = chat_provider
        self.records_by_id = {record.id: record for record in dataset.records}
        disclaimer = str(dataset.meta.get("disclaimer", "")).strip()
        self.disclaimer = disclaimer.split(".", 1)[0].removeprefix("Ескерту:").strip() or "Жалпы ақпарат."
        self.records_by_topic = defaultdict(list)
        for record in dataset.records:
            self.records_by_topic[record.topic].append(record)
        self.topic_pages.clear()


async def create_runtime(settings: Settings | None = None) -> Runtime:
    settings = settings or get_settings()
    dataset = load_dataset(settings.data_path)
    embedding_provider, chat_provider = create_providers(settings)
    search = HybridSearch(dataset, settings.cache_dir, embedding_provider)
    await search.build()
    repository = Repository(settings.database_path)
    await repository.initialize()
    await repository.prune_logs(settings.log_retention_days)
    return Runtime(settings, repository, dataset, search, embedding_provider, chat_provider)


def create_dispatcher(runtime: Runtime) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher["runtime"] = runtime
    dispatcher["repository"] = runtime.repository
    throttle = ThrottleMiddleware(runtime.settings)
    dispatcher.message.middleware(throttle)
    dispatcher.callback_query.middleware(throttle)
    dispatcher.inline_query.middleware(throttle)
    dispatcher.message.middleware(SafeLoggingMiddleware())
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
