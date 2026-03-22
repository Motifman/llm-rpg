"""仮想 SNS スナップショット DTO を LLM 向け JSON 文字列へ変換する。"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ai_rpg_world.application.social.sns_virtual_pages.page_snapshot_dtos import (
    SnsVirtualPageSnapshotDto,
)


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    return obj


def sns_snapshot_to_json(snapshot: SnsVirtualPageSnapshotDto) -> str:
    """スナップショット DTO を JSON 文字列にする（内部 ID は DTO 側で非露出）。"""
    payload = _to_jsonable(snapshot)
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["sns_snapshot_to_json"]
