import asyncio
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Sequence

import numpy as np

from bot.services.data_loader import LegalDataset, LegalRecord
from bot.services.llm import EmbeddingProvider, log_provider_failure
from bot.services.safety import mask_pii

logger = logging.getLogger(__name__)

_LATIN_TO_CYRILLIC = str.maketrans({
    "a": "а", "b": "б", "c": "с", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "һ", "i": "і", "j": "ж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р",
    "s": "с", "t": "т", "u": "ұ", "v": "в", "w": "у", "x": "х",
    "y": "ы", "z": "з",
})


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def latin_to_cyrillic(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"(?<=[a-z])ya", "я", text)
    return normalize_text(text.translate(_LATIN_TO_CYRILLIC))


def tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


@dataclass(frozen=True)
class SearchResult:
    record: LegalRecord
    score: float


class HybridSearch:
    def __init__(
        self,
        dataset: LegalDataset,
        cache_dir: Path,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.dataset = dataset
        self.cache_dir = cache_dir
        self.embedding_provider = embedding_provider
        self.records = dataset.records
        self.documents = [
            " ".join((record.question, *record.variants, record.topic))
            for record in self.records
        ]
        self.tokens = [tokenize(text) for text in self.documents]
        self.idf = self._build_idf(self.tokens)
        self.document_vectors: np.ndarray | None = None
        self._query_cache: dict[str, tuple[float, list[float]]] = {}
        self._cache_lock = asyncio.Lock()

    async def build(self) -> None:
        if self.embedding_provider is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        vector_path = self.cache_dir / "embeddings.npy"
        metadata_path = self.cache_dir / "embeddings.json"
        cache_key = self.dataset.sha256
        async with self._cache_lock:
            if vector_path.exists() and metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    if metadata.get("dataset_hash") == cache_key and metadata.get("count") == len(self.records):
                        vectors = np.load(vector_path, allow_pickle=False)
                        if vectors.shape[0] == len(self.records):
                            self.document_vectors = vectors.astype(np.float32)
                            return
                except (OSError, ValueError, json.JSONDecodeError):
                    logger.warning("Embedding cache is invalid; rebuilding it")
            try:
                vectors: list[list[float]] = []
                texts = ["passage: " + text for text in self.documents]
                for start in range(0, len(texts), 32):
                    vectors.extend(await self.embedding_provider.embed(texts[start:start + 32]))
                array = np.asarray(vectors, dtype=np.float32)
                if array.shape[0] != len(self.records):
                    raise ValueError("Embedding provider returned an unexpected number of vectors")
                np.save(vector_path, array, allow_pickle=False)
                metadata_path.write_text(
                    json.dumps({"dataset_hash": cache_key, "count": len(self.records)}),
                    encoding="utf-8",
                )
                self.document_vectors = array
            except Exception:
                log_provider_failure("embedding")
                self.embedding_provider = None

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not query.strip():
            return []
        lexical = self._lexical_scores(query)
        vector: list[float] | None = None
        if self.embedding_provider is not None and self.document_vectors is not None:
            try:
                vector = await self._embed_query(query)
            except Exception:
                log_provider_failure("query embedding")
                self.embedding_provider = None
        embedding_scores: np.ndarray | None = None
        if vector is not None:
            query_vector = np.asarray(vector, dtype=np.float32)
            embedding_scores = self.document_vectors @ query_vector / (
                np.linalg.norm(self.document_vectors, axis=1) * (np.linalg.norm(query_vector) or 1)
            )
        results: list[SearchResult] = []
        for index, record in enumerate(self.records):
            lexical_score = lexical[index]
            if embedding_scores is None:
                score = lexical_score
            else:
                score = 0.45 * lexical_score + 0.55 * max(0.0, float(embedding_scores[index]))
            results.append(SearchResult(record, max(0.0, min(1.0, score))))
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    async def _embed_query(self, query: str) -> list[float]:
        normalized = query.strip()
        now = time.monotonic()
        cached = self._query_cache.get(normalized)
        if cached and now - cached[0] < 300:
            return cached[1]
        assert self.embedding_provider is not None
        vectors = await self.embedding_provider.embed(["query: " + mask_pii(normalized)])
        if not vectors:
            raise ValueError("Embedding provider returned no query vector")
        self._query_cache[normalized] = (now, vectors[0])
        return vectors[0]

    def _lexical_scores(self, query: str) -> list[float]:
        normalized_query = normalize_text(query)
        transliterated_query = latin_to_cyrillic(normalized_query)
        query_tokens = set(tokenize(normalized_query) + tokenize(transliterated_query))
        if not query_tokens:
            return [0.0] * len(self.records)
        scores: list[float] = []
        average_length = sum(map(len, self.tokens)) / max(1, len(self.tokens))
        for record, tokens, document in zip(self.records, self.tokens, self.documents):
            token_set = set(tokens)
            matched = sum(self.idf.get(token, 0.0) for token in query_tokens & token_set)
            bm25 = matched / (matched + 2.0) if matched else 0.0
            variants = [record.question, *record.variants, record.topic, document]
            fuzzy = max(
                self._similarity(normalized_query, normalize_text(candidate))
                for candidate in variants
            )
            trans_fuzzy = max(
                self._similarity(transliterated_query, normalize_text(candidate))
                for candidate in variants
            )
            length_bonus = min(1.0, average_length / max(1, len(tokens)))
            scores.append(min(1.0, 0.55 * max(fuzzy, trans_fuzzy) + 0.4 * bm25 + 0.05 * length_bonus))
        return scores

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        try:
            from rapidfuzz.fuzz import ratio

            return ratio(left, right) / 100
        except ImportError:
            return SequenceMatcher(None, left, right).ratio()

    @staticmethod
    def _build_idf(documents: Sequence[Sequence[str]]) -> dict[str, float]:
        count = len(documents)
        frequencies: dict[str, int] = {}
        for document in documents:
            for token in set(document):
                frequencies[token] = frequencies.get(token, 0) + 1
        return {
            token: np.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in frequencies.items()
        }
