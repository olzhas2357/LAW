import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parent

SUPPORTED_LANGUAGES = ("kk", "ru", "en")
LANGUAGE_LABELS = {
    "kk": "Қазақша",
    "ru": "Русский",
    "en": "English",
}
DEFAULT_LANGUAGE = "kk"


def normalize_language(language_code: str | None) -> str:
    language = (language_code or "").split("-", 1)[0].lower()
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


@lru_cache
def messages(language: str = DEFAULT_LANGUAGE) -> dict[str, str]:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return json.loads((ROOT / f"{language}.json").read_text(encoding="utf-8"))
