import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parent


@lru_cache
def messages() -> dict[str, str]:
    return json.loads((ROOT / "kk.json").read_text(encoding="utf-8"))
