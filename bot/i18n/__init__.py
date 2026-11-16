import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parent


@lru_cache
def messages(language: str) -> dict[str, str]:
    path = ROOT / ("ru.json" if language == "ru" else "kk.json")
    return json.loads(path.read_text(encoding="utf-8"))
