import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LegalRecord:
    id: int
    source: str
    source_id: int
    topic: str
    question: str
    variants: tuple[str, ...]
    answer: str
    legal_basis: tuple[str, ...]
    confidence: str
    as_of: str


@dataclass(frozen=True)
class LegalDataset:
    meta: dict[str, Any]
    records: tuple[LegalRecord, ...]
    sha256: str

    @property
    def topics(self) -> list[str]:
        return list(self.meta.get("topics") or sorted({r.topic for r in self.records}))


def load_dataset(path: Path) -> LegalDataset:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("qa"), list):
        raise ValueError(f"{path} must contain a 'qa' array")
    records: list[LegalRecord] = []
    seen_ids: set[int] = set()
    for item in payload["qa"]:
        try:
            record = LegalRecord(
                id=int(item["id"]),
                source=str(item.get("source", "")),
                source_id=int(item.get("source_id", item["id"])),
                topic=str(item["topic"]),
                question=str(item["question"]),
                variants=tuple(str(v) for v in item.get("variants", [])),
                answer=str(item["answer"]),
                legal_basis=tuple(str(v) for v in item.get("legal_basis", [])),
                confidence=str(item["confidence"]),
                as_of=str(item.get("as_of", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid legal QA record at index {len(records)}") from exc
        if record.id in seen_ids:
            raise ValueError(f"Duplicate legal QA id: {record.id}")
        if record.confidence not in {"high", "check", "general"}:
            raise ValueError(f"Unknown confidence value for record {record.id}")
        if not record.question or not record.answer:
            raise ValueError(f"Record {record.id} must have question and answer")
        seen_ids.add(record.id)
        records.append(record)
    if not records:
        raise ValueError("Legal QA dataset is empty")
    expected_total = payload.get("meta", {}).get("total")
    if expected_total is not None and int(expected_total) != len(records):
        raise ValueError(
            f"Dataset metadata says {expected_total} records, found {len(records)}"
        )
    return LegalDataset(
        meta=payload.get("meta", {}),
        records=tuple(records),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
