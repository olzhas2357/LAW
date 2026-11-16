import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.qa import deliver_record, pick_match, pick_topic_question
from bot.handlers.start import menu_callback
from bot.handlers.topics import topics_page
from bot.keyboards import matches_keyboard, question_keyboard, rating_keyboard, topics_keyboard
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
        for language in ("kk", "ru"):
            rating = rating_keyboard(self.record.id, language)
            self.assertEqual(callbacks(rating), [f"rate:1:{self.record.id}", f"rate:0:{self.record.id}", "menu:main"])
            self.assertIn("menu:main", callbacks(topics_keyboard(self.dataset.topics, 0, language)))
            questions = question_keyboard([self.record], 0, language)
            self.assertIn("topics:0", callbacks(questions))
            self.assertIn("menu:main", callbacks(questions))
            matches = matches_keyboard([SearchResult(self.record, 0.6)], language)
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
            dataset=SimpleNamespace(topics=["Тақырып"]),
        )
        self.message = SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock())
        self.callback = SimpleNamespace(
            data="menu:main",
            from_user=SimpleNamespace(id=42),
            message=self.message,
            answer=AsyncMock(),
        )

    async def test_answer_has_localized_menu_and_ratings(self):
        await deliver_record(self.message, self.runtime, self.record, 42, user_language="ru")
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[-1][0].text, "🏠 Главное меню")
        self.assertEqual(callbacks(markup)[:2], [f"rate:1:{self.record.id}", f"rate:0:{self.record.id}"])

    async def test_long_answer_has_buttons_on_final_chunk(self):
        record = replace(self.record, answer="ақпарат " * 1200)
        await deliver_record(self.message, self.runtime, record, 42)
        calls = self.message.answer.await_args_list
        self.assertGreater(len(calls), 1)
        self.assertNotIn("reply_markup", calls[0].kwargs)
        self.assertIn("menu:main", callbacks(calls[-1].kwargs["reply_markup"]))

    async def test_menu_callback_cancels_pending_feedback_and_shows_menu(self):
        await menu_callback(self.callback, self.runtime, "ru")
        self.assertNotIn(42, self.runtime.feedback_pending)
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(callbacks(markup), ["topics:0", "emergency", "menu:help", "menu:lang"])
        self.callback.answer.assert_awaited_once()

    async def test_topic_and_match_selection_preserve_language(self):
        for handler, prefix in ((pick_match, "pick"), (pick_topic_question, "q")):
            with self.subTest(handler=prefix):
                self.callback.data = f"{prefix}:{self.record.id}"
                await handler(self.callback, self.runtime, "ru")
                markup = self.message.answer.await_args.kwargs["reply_markup"]
                self.assertEqual(markup.inline_keyboard[-1][0].text, "🏠 Главное меню")

    async def test_return_to_topics_updates_title(self):
        self.callback.data = "topics:0"
        await topics_page(self.callback, self.runtime, "ru")
        self.assertEqual(self.message.edit_text.await_args.args[0], "Выберите тему:")
        self.assertIn("menu:main", callbacks(self.message.edit_text.await_args.kwargs["reply_markup"]))


if __name__ == "__main__":
    unittest.main()
