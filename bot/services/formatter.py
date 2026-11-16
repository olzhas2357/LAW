from bot.services.data_loader import LegalRecord
from bot.services.safety import mask_pii

DISCLAIMER_SHORT = "ℹ️ Жалпы ақпарат. Нақты жағдай бойынша заңгермен кеңесіңіз."


def format_answer(
    answer: str,
    record: LegalRecord | None = None,
    disclaimer: str = DISCLAIMER_SHORT,
) -> str:
    parts = [mask_pii(answer.strip())]
    if record and record.confidence == "check":
        parts.append("⚠️ Бап нөмірі мен мерзімді adilet.zan.kz сайтынан тексеріңіз.")
    if record and record.legal_basis:
        parts.append("📚 Құқықтық негіз: " + "; ".join(record.legal_basis))
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
