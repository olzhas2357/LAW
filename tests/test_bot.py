import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from bot.config import Settings
from bot.db.repo import Repository
from bot.i18n import messages
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

    def test_localized_datasets_share_record_ids_and_have_translated_content(self):
        datasets = {
            language: load_dataset(ROOT / f"legal_bot_{language}.json")
            for language in ("en", "ru")
        }
        kazakh = load_dataset(ROOT / "legal_bot.json")
        expected_ids = {record.id for record in kazakh.records}
        for language, dataset in datasets.items():
            with self.subTest(language=language):
                self.assertEqual(dataset.meta["language"], language)
                self.assertEqual({record.id for record in dataset.records}, expected_ids)
                self.assertNotEqual(dataset.records[0].question, kazakh.records[0].question)

    def test_translation_files_have_the_same_message_keys(self):
        keys = set(messages("kk"))
        self.assertEqual(set(messages("ru")), keys)
        self.assertEqual(set(messages("en")), keys)


class SafetyTests(unittest.TestCase):
    def test_emergency_phrases_kazakh_and_russian(self):
        self.assertTrue(is_emergency("Күйеуім мені ұрады"))
        self.assertTrue(is_emergency("Он угрожает и избивает меня"))
        self.assertTrue(is_emergency("He threatened to kill me"))
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
    async def test_language_preference_is_persisted_and_old_users_migrate(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "bot.db"
            with sqlite3.connect(database_path) as db:
                db.execute(
                    "CREATE TABLE users (user_id INTEGER PRIMARY KEY, created_at TEXT NOT NULL)"
                )
                db.execute(
                    "INSERT INTO users(user_id, created_at) VALUES (42, '2026-01-01')"
                )

            repository = Repository(database_path)
            await repository.initialize()
            self.assertEqual(await repository.get_language(42), "kk")
            await repository.set_language(42, "en")
            self.assertEqual(await repository.get_language(42), "en")

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
            self.assertEqual(runtime.for_language("ru").dataset.meta["language"], "ru")
            self.assertEqual(runtime.for_language("en").dataset.meta["language"], "en")
            english = runtime.for_language("en")
            question = english.dataset.records[20].question
            result = await english.search.search(question, limit=1)
            self.assertEqual(result[0].record.question, question)
            self.assertIsNotNone(dispatcher)
            self.assertTrue((root / "bot.db").exists())


if __name__ == "__main__":
    unittest.main()
