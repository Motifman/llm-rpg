from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ObjectDescriptionVariant:
    """オブジェクト説明の状態依存差し替えルール。"""

    description: str
    required_state: Optional[dict[str, Any]] = None
    required_flag: Optional[str] = None
