import re
import unicodedata

EMERGENCY_NUMBERS = (
    "🚨 Шұғыл көмек: 102 — полиция, 103 — жедел жәрдем, "
    "112 — бірыңғай құтқару қызметі, 111 — балалар мен отбасыға көмек."
)
SUPPORT_TEXT = (
    "Сіз бұған кінәлі емессіз. Қауіпсіз жерге өтіп, сенімді адамға хабарласыңыз. "
    "Қазір қауіп төніп тұрса, шұғыл қызметке бірден қоңырау шалыңыз."
)
_DANGER_TERMS = (
    "ұрамын", "ұрады", "ұрып", "ұрды", "соққы", "зорлық", "шантаж", "қорқытып", "өлтіремін",
    "өлтір", "өзіме қол жұмса", "суицид", "өміріме қауіп", "ұрлап", "зорлады",
    "жыныстық зорлық", "избивает", "побои", "насилие", "шантаж", "угрожает",
    "убью", "убить", "самоубийств", "покончить с собой", "похит", "изнасил",
    "опасность жизни", "бьет", "бьёт", "избил", "избивает", "избивают",
    "изнасил", "домог", "угроз", "покончить", "не хочу жить", "хочу умереть",
    "вред себе", "порезать себя", "меня заставляют",
    "hit me", "hits me", "beat me", "beating me", "violence", "blackmail",
    "threaten", "threatens", "kill me", "kill myself", "suicide", "end my life",
    "hurt myself", "self harm", "kidnap", "rape", "sexual assault", "stalking",
    "domestic abuse", "in danger", "force me",
)


def normalize_for_safety(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return re.sub(r"[^\w\s]", " ", normalized)


def is_emergency(text: str) -> bool:
    normalized = normalize_for_safety(text)
    return any(term in normalized for term in _DANGER_TERMS)


def mask_pii(text: str) -> str:
    """Redact common direct identifiers before logging or external API calls."""
    masked = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email]", text)
    masked = re.sub(r"(?<!\d)(?:\+?7|8)?[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)", "[телефон]", masked)
    masked = re.sub(r"(?<!\d)\d{12}(?!\d)", "[ЖСН]", masked)
    masked = re.sub(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)", "[карта]", masked)
    return masked


def contains_sensitive_data(text: str) -> bool:
    return mask_pii(text) != text
