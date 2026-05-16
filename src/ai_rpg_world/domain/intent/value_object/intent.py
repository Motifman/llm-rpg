"""``Intent`` 値オブジェクト。

LLM がツール呼び出しを通じて「こうしたい」と意図した内容の不変記述。
即時 mutate ではなく queue に積み、tick 内の resolve フェーズで validate +
実行される。

設計メモ
--------
- ``arguments`` は読み取り専用相当の Mapping。LLM が返す JSON をそのまま
  保持するため辞書の値は任意の primitive / list / dict を許容する。VO の
  内部で deep-immutable には変換せず、呼び出し側が新しい dict を渡すことで
  共有汚染を防ぐ運用とする (DTO の慣習に従う)。
- ``submitted_at_tick`` と ``complete_at_tick`` を分けることで PR6 (アクション
  持続時間) を破壊的変更なしに乗せられる。当面 instant action の場合は両者を
  同じ tick にしておけばよい。
- ``target_descriptor`` は late-binding 用の意図記述 (例:
  ``{"label": "前にいるゴブリン"}``)。解決時に現在の世界状態に対して
  マッチングする。PR6 以降の機能だが、フィールドだけ予約する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.exception.intent_exception import (
    IntentValidationException,
)
from ai_rpg_world.domain.intent.value_object.intent_id import IntentId
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase
from ai_rpg_world.domain.intent.value_object.intent_priority import (
    IntentPriority,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class Intent:
    """LLM tool 呼び出しの意図記述。

    Attributes
    ----------
    intent_id:
        tick 全体で一意な識別子。
    player_id:
        intent を投稿したプレイヤー (LLM エージェント)。
    tool_name:
        ツール名 (例: ``spot_graph_travel_to`` / ``attack`` / ``say``)。
    arguments:
        ツール引数の Mapping。dict の値は LLM 由来の primitive / list / dict
        を許容する。**注意**: Intent は frozen だが ``arguments`` 内のネスト
        した値はコピーされない。submit 後に呼び出し側が dict を mutate しない
        運用とする (DTO の慣習に従う)。
    phase:
        同一 tick 内での解決フェーズ。
    submitted_at_tick:
        intent が queue に積まれた tick。
    complete_at_tick:
        intent が解決される予定の tick。``submitted_at_tick`` と同じ場合は
        instant action として即 tick で解決される。
    priority:
        同一フェーズ内のさらに細かい解決順 (大きい方が先)。
    target_descriptor:
        late-binding 用の意図記述。``None`` の場合は ``arguments`` の
        従来通りの ID 指定で解決する。**注意**: ``arguments`` と同様、ネストした
        値は不変ではない。
    """

    intent_id: IntentId
    player_id: PlayerId
    tool_name: str
    arguments: Mapping[str, Any]
    phase: IntentPhase
    submitted_at_tick: WorldTick
    complete_at_tick: WorldTick
    priority: IntentPriority = field(default_factory=IntentPriority)
    target_descriptor: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent_id, IntentId):
            raise IntentValidationException("intent_id must be IntentId")
        if not isinstance(self.player_id, PlayerId):
            raise IntentValidationException("player_id must be PlayerId")
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise IntentValidationException("tool_name must be non-empty str")
        if not isinstance(self.arguments, Mapping):
            raise IntentValidationException("arguments must be Mapping")
        if not isinstance(self.phase, IntentPhase):
            raise IntentValidationException("phase must be IntentPhase")
        if not isinstance(self.submitted_at_tick, WorldTick):
            raise IntentValidationException(
                "submitted_at_tick must be WorldTick"
            )
        if not isinstance(self.complete_at_tick, WorldTick):
            raise IntentValidationException(
                "complete_at_tick must be WorldTick"
            )
        if self.complete_at_tick.value < self.submitted_at_tick.value:
            raise IntentValidationException(
                "complete_at_tick must be >= submitted_at_tick"
            )
        if not isinstance(self.priority, IntentPriority):
            raise IntentValidationException(
                "priority must be IntentPriority"
            )
        if self.target_descriptor is not None and not isinstance(
            self.target_descriptor, Mapping
        ):
            raise IntentValidationException(
                "target_descriptor must be Mapping or None"
            )

    @property
    def is_instant(self) -> bool:
        """instant action (持続時間 0 tick) かどうか。"""
        return self.complete_at_tick.value == self.submitted_at_tick.value
