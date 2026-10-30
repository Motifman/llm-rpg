"""公開SNSの内容・不変識別子・開いている画面・通知表示状態を一緒に保存する。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import WorldSubsystemCodec
from ai_rpg_world.application.social.public_sns.prompt_projection import PublicSnsPromptProjection
from ai_rpg_world.application.social.public_sns.retained_screen import PublicSnsScreenStore
from ai_rpg_world.infrastructure.repository.public_sns_snapshot_codec import (
    capture_public_sns_store,
    restore_public_sns_store,
)


class PublicSnsSubsystemCodec(WorldSubsystemCodec):
    @property
    def subsystem_key(self) -> str:
        return "public_sns"

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_public_sns_data_store", None)
        screens = getattr(runtime, "_public_sns_screens", PublicSnsScreenStore())
        projection = getattr(runtime, "_public_sns_projection", None)
        return {
            "schema_version": 1,
            "enabled": store is not None,
            "store": capture_public_sns_store(store) if store else None,
            "screens": screens.capture(),
            "projection": projection.capture() if projection else None,
            "execution_turns": {str(pid): turn for pid, turn in getattr(runtime, "_execution_turns", {}).items()},
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        store = getattr(runtime, "_public_sns_data_store", None)
        if data.get("schema_version") != 1 or type(data.get("enabled")) is not bool:
            raise ValueError("公開SNSの保存形式が不正です")
        if data["enabled"] != (store is not None):
            raise ValueError("公開SNSの有効状態が保存時と異なります")
        screens = PublicSnsScreenStore()
        screens.restore(data["screens"])
        turns = data.get("execution_turns")
        if not isinstance(turns, dict):
            raise ValueError("実行手番の保存形式が不正です")
        decoded_turns = {}
        for pid, turn in turns.items():
            if not isinstance(pid, str) or not pid.isdecimal() or type(turn) is not int or turn < 0:
                raise ValueError("実行手番の保存形式が不正です")
            decoded_turns[int(pid)] = turn
        projection = None
        if store is not None:
            projection = PublicSnsPromptProjection(screens, budget_chars=runtime.scenario.public_sns_push_budget_chars)
            projection.restore(data["projection"])
            # 最後に集約内容を検査して一括置換する。前段の表示検査が失敗しても
            # 実行中のSNS内容を変更せずに止まる。
            restore_public_sns_store(store, data["store"])
        elif data.get("store") is not None or data.get("projection") is not None:
            raise ValueError("無効な公開SNSに内容が保存されています")
        runtime._public_sns_screens.restore(screens.capture())
        if projection is not None:
            runtime._public_sns_projection.restore(projection.capture())
        runtime._execution_turns = decoded_turns
