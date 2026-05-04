from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ObjectDescriptionVariant:
    """オブジェクト説明の状態依存差し替えルール。

    requires_read=True のバリアントは、そのオブジェクトを「読む」操作をした
    エージェントにのみ表示される（手紙の内容、暗号のヒント等）。
    """

    description: str
    required_state: Optional[dict[str, Any]] = None
    required_flag: Optional[str] = None
    requires_read: bool = False
