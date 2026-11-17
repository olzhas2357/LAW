from bot.services.data_loader import LegalRecord
from bot.services.safety import mask_pii
from bot.i18n import messages as translations

DISCLAIMER_SHORT = translations()["disclaimer_short"]


def format_answer(
    answer: str,
    record: LegalRecord | None = None,
    disclaimer: str = DISCLAIMER_SHORT,
    language: str = "kk",
) -> str:
    text = translations(language)
    parts = [mask_pii(answer.strip())]
    if record and record.confidence == "check":
        parts.append(text["confidence_check"])
    if record and record.legal_basis:
        parts.append(text["legal_basis"] + "; ".join(record.legal_basis))
    parts.append("ℹ️ " + disclaimer)
    return "\n\n".join(parts)


def split_message(text: str, limit: int = 4096) -> list[str]:
    chunks: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = text.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks
