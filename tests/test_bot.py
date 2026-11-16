import asyncio
import tempfile
import unittest
from pathlib import Path

from bot.config import Settings
from bot.main import create_dispatcher, create_runtime
from bot.services.data_loader import load_dataset
from bot.services.formatter import split_message
from bot.services.safety import contains_sensitive_data, is_emergency, mask_pii
from bot.services.search import HybridSearch, latin_to_cyrillic

ROOT = Path(__file__).resolve().parents[1]


class DataTests(unittest.TestCase):
    def test_dataset_schema_and_count(self):
        dataset = load_dataset(ROOT / "legal_bot.json")
        self.assertEqual(len(dataset.records), 222)
        self.assertEqual(len(dataset.topics), 34)
        self.assertEqual(dataset.records[0].id, 1)


class SafetyTests(unittest.TestCase):
    def test_emergency_phrases_kazakh_and_russian(self):
        self.assertTrue(is_emergency("Күйеуім мені ұрады"))
        self.assertTrue(is_emergency("Он угрожает и избивает меня"))
        self.assertFalse(is_emergency("Как оформить трудовой договор?"))

    def test_pii_is_masked(self):
        text = "Телефон +7 701 123 45 67, ИИН 123456789012, mail a@b.kz"
        masked = mask_pii(text)
        self.assertNotIn("123456789012", masked)
        self.assertNotIn("a@b.kz", masked)
        self.assertTrue(contains_sensitive_data(text))


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.dataset = load_dataset(ROOT / "legal_bot.json")
        self.search = HybridSearch(self.dataset, ROOT / "cache")

    def test_exact_dataset_question_ranks_first(self):
        record = self.dataset.records[20]
        result = asyncio.run(self.search.search(record.question, limit=1))[0]
        self.assertEqual(result.record.id, record.id)
        self.assertGreaterEqual(result.score, 0.78)

    def test_romanized_kazakh_is_normalized(self):
        self.assertEqual(latin_to_cyrillic("alayaqtyq"), "алаяқтық")

    def test_romanized_topic_finds_data(self):
        results = asyncio.run(self.search.search("alayaqtyq", limit=3))
        self.assertTrue(any("алаяқтық" in item.record.topic.casefold() for item in results))


class FormatterTests(unittest.TestCase):
    def test_message_chunks_obey_telegram_limit(self):
        chunks = split_message(("legal information " * 700).strip(), limit=4096)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4096 for chunk in chunks))


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_initializes_database_and_dispatcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(
                _env_file=None,
                bot_token="test-token",
                data_path=ROOT / "legal_bot.json",
                database_path=root / "bot.db",
                cache_dir=root / "cache",
                llm_provider="none",
            )
            runtime = await create_runtime(settings)
            dispatcher = create_dispatcher(runtime)
            self.assertEqual(len(runtime.records_by_id), 222)
            self.assertEqual(len(runtime.records_by_topic), 34)
            self.assertIsNotNone(dispatcher)
            self.assertTrue((root / "bot.db").exists())


if __name__ == "__main__":
    unittest.main()
