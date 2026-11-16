import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.config import Settings
from bot.handlers.qa import deliver_record, explain_record, handle_question
from bot.i18n import messages
from bot.services.data_loader import load_dataset
from bot.services.llm import ChatCompletionResult, InvalidChatCompletion, OpenAIProvider, create_providers
from bot.services.safety import EMERGENCY_NUMBERS
from bot.services.search import SearchResult

ROOT = Path(__file__).resolve().parents[1]


class AIHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.record = load_dataset(ROOT / "legal_bot.json").records[0]
        self.provider = SimpleNamespace(
            answer=AsyncMock(return_value=ChatCompletionResult("Толық жауап", 200, 0.002)),
        )
        self.repository = SimpleNamespace(
            usage_today=AsyncMock(return_value=(0, 0)),
            record_usage=AsyncMock(),
            log_question=AsyncMock(),
            register_user=AsyncMock(),
        )
        self.runtime = SimpleNamespace(
            settings=SimpleNamespace(
                use_llm=True,
                search_top_k=5,
                search_low_threshold=0.35,
                search_high_threshold=0.78,
                openai_daily_token_limit=1000,
                openai_daily_cost_limit_usd=1,
            ),
            chat_provider=self.provider,
            repository=self.repository,
            search=SimpleNamespace(search=AsyncMock(return_value=[SearchResult(self.record, 0.5)])),
            records_by_id={self.record.id: self.record},
            disclaimer="Жалпы ақпарат",
            topic_menu=lambda: "topics",
        )
        self.message = SimpleNamespace(
            text="Құқықтарым туралы айтып беріңіз: a@b.kz",
            from_user=SimpleNamespace(id=42),
            chat=SimpleNamespace(id=42),
            bot=SimpleNamespace(send_chat_action=AsyncMock()),
            answer=AsyncMock(),
        )
        self.callback = SimpleNamespace(
            data=f"detail:{self.record.id}",
            from_user=self.message.from_user,
            message=self.message,
            answer=AsyncMock(),
        )

    async def test_free_question_uses_relevant_context_and_masks_personal_data(self):
        other = load_dataset(ROOT / "legal_bot.json").records[1]
        self.runtime.search.search.return_value = [
            SearchResult(self.record, 0.5),
            SearchResult(other, 0.2),
        ]
        await handle_question(self.message, self.runtime)
        question, records = self.provider.answer.await_args.args
        self.assertNotIn("a@b.kz", question)
        self.assertEqual(records, [self.record])
        self.repository.record_usage.assert_awaited_once_with(42, 200, 0.002)
        self.assertIn("Толық жауап", self.message.answer.await_args.args[0])
        self.assertIn(messages()["ai_context"], self.message.answer.await_args.args[0])
        self.assertIn(self.record.question, self.message.answer.await_args.args[0])
        self.assertNotIn(other.question, self.message.answer.await_args.args[0])
        self.assertFalse(self.repository.log_question.await_args.kwargs["track_unanswered"])

    async def test_no_relevant_records_does_not_call_ai(self):
        self.runtime.search.search.return_value = [SearchResult(self.record, 0.2)]
        await handle_question(self.message, self.runtime)
        self.provider.answer.assert_not_awaited()
        self.assertIn(messages()["no_answer"], self.message.answer.await_args.args[0])
        self.assertNotIn("track_unanswered", self.repository.log_question.await_args.kwargs)

    async def test_high_confidence_free_question_uses_at_most_three_records(self):
        records = load_dataset(ROOT / "legal_bot.json").records[:4]
        self.runtime.search.search.return_value = [SearchResult(record, 0.9) for record in records]
        await handle_question(self.message, self.runtime)
        self.assertEqual(self.provider.answer.await_args.args[1], list(records[:3]))
        self.assertIn("Толық жауап", self.message.answer.await_args.args[0])

    async def test_disabled_ai_preserves_search_selection(self):
        self.runtime.settings.use_llm = False
        await handle_question(self.message, self.runtime)
        self.provider.answer.assert_not_awaited()
        self.assertEqual(self.message.answer.await_args.args[0], messages()["ask"])

    async def test_provider_failure_notifies_and_falls_back_to_dataset(self):
        self.provider.answer.side_effect = RuntimeError("API error")
        self.runtime.search.search.return_value = [SearchResult(self.record, 0.9)]
        with self.assertLogs("bot.handlers.qa", level="ERROR"):
            await handle_question(self.message, self.runtime)
        texts = [call.args[0] for call in self.message.answer.await_args_list]
        self.assertIn(messages()["ai_unavailable"], texts)
        self.assertIn(self.record.answer, texts[-1])

    async def test_usage_limit_notifies_and_skips_provider(self):
        self.repository.usage_today.return_value = (1000, 0)
        with self.assertLogs("bot.handlers.qa", level="WARNING"):
            await handle_question(self.message, self.runtime)
        self.provider.answer.assert_not_awaited()
        self.assertIn(messages()["ai_unavailable"], [call.args[0] for call in self.message.answer.await_args_list])
        self.assertEqual(self.message.answer.await_args.args[0], messages()["ask"])

    async def test_incomplete_response_is_accounted_and_not_shown(self):
        self.provider.answer.side_effect = InvalidChatCompletion("truncated", 300, 0.003)
        with self.assertLogs("bot.handlers.qa", level="ERROR"):
            await handle_question(self.message, self.runtime)
        self.repository.record_usage.assert_awaited_once_with(42, 300, 0.003)
        self.assertIn(messages()["ai_unavailable"], [call.args[0] for call in self.message.answer.await_args_list])

    async def test_emergency_notice_precedes_ai_answer(self):
        self.message.text = "Күйеуім мені ұрады"
        await handle_question(self.message, self.runtime)
        self.assertIn(EMERGENCY_NUMBERS, self.message.answer.await_args_list[0].args[0])
        self.assertIn("Толық жауап", self.message.answer.await_args.args[0])

    async def test_dataset_answer_offers_details_only_when_enabled(self):
        await deliver_record(self.message, self.runtime, self.record, 42)
        self.provider.answer.assert_not_awaited()
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn(f"detail:{self.record.id}", callbacks)
        self.runtime.settings.use_llm = False
        await deliver_record(self.message, self.runtime, self.record, 42)
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertNotIn(f"detail:{self.record.id}", callbacks)

    async def test_detail_button_uses_selected_record_and_accounts_usage(self):
        await explain_record(self.callback, self.runtime)
        self.callback.answer.assert_awaited_once()
        self.provider.answer.assert_awaited_once_with(self.record.question, [self.record])
        self.repository.record_usage.assert_awaited_once_with(42, 200, 0.002)
        self.assertIn("Толық жауап", self.message.answer.await_args.args[0])
        markup = self.message.answer.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertNotIn(f"detail:{self.record.id}", callbacks)
        self.assertIn(f"rate:1:{self.record.id}", callbacks)

    async def test_detail_button_after_record_removed_is_acknowledged(self):
        self.runtime.records_by_id.clear()
        await explain_record(self.callback, self.runtime)
        self.callback.answer.assert_awaited_once_with(messages()["detail_missing"], show_alert=True)
        self.provider.answer.assert_not_awaited()

    async def test_detail_button_handles_disabled_provider(self):
        self.runtime.chat_provider = None
        await explain_record(self.callback, self.runtime)
        self.callback.answer.assert_awaited_once()
        self.assertEqual(self.message.answer.await_args.args[0], messages()["ai_unavailable"])

    async def test_detail_button_handles_provider_failure(self):
        self.provider.answer.side_effect = RuntimeError("API error")
        with self.assertLogs("bot.handlers.qa", level="ERROR"):
            await explain_record(self.callback, self.runtime)
        self.callback.answer.assert_awaited_once()
        self.assertEqual(self.message.answer.await_args.args[0], messages()["ai_unavailable"])


class OpenAIProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.record = load_dataset(ROOT / "legal_bot.json").records[0]
        self.create = AsyncMock()
        self.provider = OpenAIProvider.__new__(OpenAIProvider)
        self.provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))
        self.provider.chat_model = "test-model"
        self.provider.cost_per_1k_tokens = 0.001

    async def test_detail_response_and_token_budget(self):
        self.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=" Жауап "))],
            usage=SimpleNamespace(total_tokens=200),
        )
        result = await self.provider.answer("Email a@b.kz", [self.record])
        self.assertEqual(result.text, "Жауап")
        self.assertEqual(result.tokens, 200)
        self.assertEqual(self.create.await_args.kwargs["max_tokens"], 1800)
        self.assertNotIn("a@b.kz", self.create.await_args.kwargs["messages"][1]["content"])

    async def test_truncated_response_is_rejected(self):
        self.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content="Аяқталмаған"))],
            usage=SimpleNamespace(total_tokens=300),
        )
        with self.assertRaisesRegex(InvalidChatCompletion, "truncated") as error:
            await self.provider.answer("Сұрақ", [self.record])
        self.assertEqual(error.exception.tokens, 300)
        self.assertAlmostEqual(error.exception.cost_usd, 0.0003)

    def test_enabled_ai_requires_provider_and_key(self):
        settings = Settings(_env_file=None, use_llm=True, llm_provider="none")
        with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
            create_providers(settings)


if __name__ == "__main__":
    unittest.main()
