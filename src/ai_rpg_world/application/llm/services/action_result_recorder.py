"""行動結果の記録 + 直後の記憶 hook を 1 箇所に束ねる共有サービス (U1)。

従来 world_runtime._record_action_result が inline で持っていた
「action store append → chunk_coordinator.after_action_recorded →
semantic_promotion.on_after_tool_turn」を共有コアに抽出する。escape runtime は
この recorder への thin delegate になり、挙動は不変 (#553 で contract 化済み)。

# 設計判断

- **hook 順序は escape baseline**: append → chunk → promotion。full orchestrator は
  append と chunk の間に loop_guard を挟むため、loop_guard はこの recorder に
  含めず呼び出し側に残す。なお ``record()`` は append→chunk→promotion を一体で
  実行する粒度なので、full path がこのまま drop-in 採用できるわけではない
  (full の append→loop_guard→chunk 順に挿入するには append と after-append hooks を
  分離する / after_append callback を受ける等の API 調整が要る)。これは U-later の
  full 採用時に詰める。
- **error isolation**: chunk / promotion が例外を投げても logger.exception で記録し、
  append 済みの action 完了は止めない (memory pipeline の失敗を行動完了に波及させない)。
- **episodic_stack は呼び出しごとに受ける**: stack は runtime 構築後に遅延配線
  されるため、recorder は保持せず record() の引数で受ける。``None`` なら記憶 hook
  を skip (= episodic OFF)。
- subjective fields (expected_result / intention / emotion_hint) や fingerprint 等は
  optional 引数として通す口を用意する。escape は当面 subset しか渡さない (U2 で配線)。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from ai_rpg_world.application.llm.contracts.interfaces import IActionResultStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ActionResultRecorder:
    """action 記録 + chunk write + semantic promotion を束ねる (escape baseline 順序)。"""

    def __init__(
        self, action_result_store: IActionResultStore, *, logger: Optional[logging.Logger] = None
    ) -> None:
        if action_result_store is None:
            raise TypeError("action_result_store must not be None")
        self._store = action_result_store
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def record(
        self,
        player_id: PlayerId,
        *,
        action_summary: str,
        result_summary: str,
        occurred_at: Optional[datetime] = None,
        tool_name: Optional[str] = None,
        success: bool = True,
        error_code: Optional[str] = None,
        scene_boundary: bool = False,
        occurred_tick: Optional[int] = None,
        game_time_label: Optional[str] = None,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
        argument_fingerprint: Optional[str] = None,
        should_reschedule: bool = False,
        omit_result_in_prompt: bool = False,
        episodic_stack: Optional[Any] = None,
    ) -> None:
        """action を store に積み、episodic_stack があれば chunk → promotion を回す。"""
        self._store.append(
            player_id,
            action_summary=action_summary,
            result_summary=result_summary,
            occurred_at=occurred_at,
            success=success,
            error_code=error_code,
            tool_name=tool_name,
            argument_fingerprint=argument_fingerprint,
            should_reschedule=should_reschedule,
            game_time_label=game_time_label,
            omit_result_in_prompt=omit_result_in_prompt,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
            scene_boundary=scene_boundary,
            occurred_tick=occurred_tick,
        )
        if episodic_stack is None:
            return
        pid_value = getattr(player_id, "value", player_id)
        # append 後に chunk write。失敗は記録して action 完了は止めない。
        try:
            episodic_stack.chunk_coordinator.after_action_recorded(player_id)
        except Exception:
            self._logger.exception(
                "episodic chunk_coordinator.after_action_recorded failed for player=%s",
                pid_value,
            )
        # chunk write 直後に semantic promotion (semantic 有効時のみ非 None)。
        promotion = getattr(episodic_stack, "episodic_semantic_promotion", None)
        if promotion is not None:
            try:
                promotion.on_after_tool_turn(pid_value)
            except Exception:
                self._logger.exception(
                    "episodic_semantic_promotion.on_after_tool_turn failed for player=%s",
                    pid_value,
                )


__all__ = ["ActionResultRecorder"]
