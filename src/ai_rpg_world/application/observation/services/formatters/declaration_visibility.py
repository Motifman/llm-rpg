from __future__ import annotations

from typing import Optional


def declaration_hides_actor(message: Optional[str]) -> bool:
    """宣言文に ``{actor}`` が無ければ構造化データからも行為者を伏せる。"""
    normalized = (message or "").strip()
    return bool(normalized) and "{actor}" not in normalized
