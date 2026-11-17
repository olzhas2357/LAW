import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.qa import deliver_record, pick_match, pick_topic_question
from bot.handlers.start import menu_callback, select_language
from bot.handlers.topics import topics_page
from bot.keyboards import matches_keyboard, question_keyboard, rating_keyboard, topics_keyboard
from bot.middlewares.language import LanguageMiddleware
from bot.services.data_loader import load_dataset
from bot.services.search import SearchResult

ROOT = Path(__file__).resolve().parents[1]


def callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class KeyboardTests(unittest.TestCase):
    def setUp(self):
        self.dataset = load_dataset(ROOT / "legal_bot.json")
        self.record = self.dataset.records[0]

    def test_navigation_and_feedback_buttons(self):
        rating = rating_keyboard(self.record.id)
        self.assertEqual(callbacks(rating), [f"rate:1:{self.record.id}", f"rate:0:{self.record.id}", "menu:main"])
        self.assertIn("menu:main", callbacks(topics_keyboard(self.dataset.topics, 0)))
        questions = question_keyboard([self.record], 0)
        self.assertIn("topics:0", callbacks(questions))
        self.assertIn("menu:main", callbacks(questions))
        matches = matches_keyboard([SearchResult(self.record, 0.6)])
        self.assertIn("menu:main", callbacks(matches))


class MenuHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.record = load_dataset(ROOT / "legal_bot.json").records[0]
        self.runtime = SimpleNamespace(
            chat_provider=None,
            settings=SimpleNamespace(use_llm=False),
            disclaimer="Жалпы ақпарат",
            records_by_id={self.record.id: self.record},
            repository=SimpleNamespace(log_question=AsyncMock()),
            feedback_pending={42: self.record.id},
            topic_pages={42: self.record.topic},
            dataset=SimpleNamespace(topics=["Тақырып"]),
        )
        self.message = SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock())
        self.callback = SimpleNamespace(
            data="menu:main",
            from_user=SimpleNamespace(id=42),
            message=self.message,
            answer=AsyncMock(),
        )

    async def test_answer_has_kazakh_menu_and_ratings(self):
        await deliver_record(self.message, self.runtime, self.record, 42)
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[-1][0].text, "🏠 Басты мәзір")
        self.assertEqual(callbacks(markup)[:2], [f"rate:1:{self.record.id}", f"rate:0:{self.record.id}"])

    async def test_long_answer_has_buttons_on_final_chunk(self):
        record = replace(self.record, answer="ақпарат " * 1200)
        await deliver_record(self.message, self.runtime, record, 42)
        calls = self.message.answer.await_args_list
        self.assertGreater(len(calls), 1)
        self.assertNotIn("reply_markup", calls[0].kwargs)
        self.assertIn("menu:main", callbacks(calls[-1].kwargs["reply_markup"]))

    async def test_menu_callback_cancels_pending_feedback_and_shows_menu(self):
        await menu_callback(self.callback, self.runtime)
        self.assertNotIn(42, self.runtime.feedback_pending)
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(callbacks(markup), ["topics:0", "emergency", "menu:help", "menu:language"])
        self.callback.answer.assert_awaited_once()

    async def test_language_selection_persists_and_shows_localized_menu(self):
        repository = SimpleNamespace(set_language=AsyncMock())
        self.runtime.repository = repository
        self.callback.data = "language:ru"
        await select_language(self.callback, self.runtime)
        repository.set_language.assert_awaited_once_with(42, "ru")
        self.assertNotIn(42, self.runtime.topic_pages)
        self.assertNotIn(42, self.runtime.feedback_pending)
        self.assertIn("русский", self.message.answer.await_args.args[0].lower())
        self.assertEqual(callbacks(self.message.answer.await_args.kwargs["reply_markup"])[-1], "menu:language")

    async def test_language_middleware_detects_and_persists_telegram_language(self):
        repository = SimpleNamespace(
            get_language=AsyncMock(return_value=None),
            set_language=AsyncMock(),
        )
        runtime = SimpleNamespace(
            repository=repository,
            for_language=lambda language: SimpleNamespace(language=language),
        )
        event = SimpleNamespace(
            from_user=SimpleNamespace(id=42, language_code="en-US"),
        )
        received = {}

        async def handler(update, data):
            received["update"] = update
            received["runtime"] = data["runtime"]

        await LanguageMiddleware()(handler, event, {"runtime": runtime})
        repository.set_language.assert_awaited_once_with(42, "en")
        self.assertIs(received["update"], event)
        self.assertEqual(received["runtime"].language, "en")

    async def test_topic_and_match_selection_use_kazakh_menu(self):
        for handler, prefix in ((pick_match, "pick"), (pick_topic_question, "q")):
            with self.subTest(handler=prefix):
                self.callback.data = f"{prefix}:{self.record.id}"
                await handler(self.callback, self.runtime)
                markup = self.message.answer.await_args.kwargs["reply_markup"]
                self.assertEqual(markup.inline_keyboard[-1][0].text, "🏠 Басты мәзір")

    async def test_return_to_topics_updates_title(self):
        self.callback.data = "topics:0"
        await topics_page(self.callback, self.runtime)
        self.assertEqual(self.message.edit_text.await_args.args[0], "Тақырыпты таңдаңыз:")
        self.assertIn("menu:main", callbacks(self.message.edit_text.await_args.kwargs["reply_markup"]))


if __name__ == "__main__":
    unittest.main()
