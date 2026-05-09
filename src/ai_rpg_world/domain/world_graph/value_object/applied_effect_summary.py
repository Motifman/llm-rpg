"""適用された効果の構造化サマリ。

`WorldGraphEffectService.apply_effects` が visibility 別バケットに集計し、
- ACTOR_DIRECT は行為者のツール結果へ直接返す
- PUBLIC_OBSERVABLE は同スポットの第三者に観測イベントとして配信
- HIDDEN は本人プロンプトの現在状態にのみ反映（観測には載せない）

を行うために使う構造化された記述。Phase 4 までは「変わったかどうか」の
boolean しか持っていなかったが、LLM に「何がどう変わったか」を伝えるため
state delta を含む形で持つ。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple

from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility


class AppliedEffectKind(Enum):
    """サマリに載せる効果の種別。"""

    ACTING_ITEM_STATE_CHANGE = "ACTING_ITEM_STATE_CHANGE"
    TARGET_ITEM_STATE_CHANGE = "TARGET_ITEM_STATE_CHANGE"
    ACTING_PLAYER_STATE_CHANGE = "ACTING_PLAYER_STATE_CHANGE"
    SPOT_OBJECT_STATE_CHANGE = "SPOT_OBJECT_STATE_CHANGE"
    DAMAGE = "DAMAGE"
    STATUS_EFFECT = "STATUS_EFFECT"
    SATISFY_NEED = "SATISFY_NEED"
    TELEPORT = "TELEPORT"
    ATMOSPHERE_UPDATE = "ATMOSPHERE_UPDATE"
    PASSAGE_STATE_UPDATE = "PASSAGE_STATE_UPDATE"
    CONNECTION_CREATED = "CONNECTION_CREATED"
    CONNECTION_DESTROYED = "CONNECTION_DESTROYED"


@dataclass(frozen=True)
class StateDeltaEntry:
    """state map の 1 キー分の変更。

    before が None の場合は新規キー、after が None の場合は削除を表す。
    JSON serializable な値のみ。
    """

    key: str
    before: Any
    after: Any


@dataclass(frozen=True)
class AppliedEffectSummary:
    """適用された 1 効果の構造化サマリ。

    `target_ref` は人間 / LLM 向けの参照識別子（例: spot_object 名や item_spec_id）。
    `description` は LLM 向けに整形された 1 行の自然言語要約。
    `state_delta` は state マップ系の変更を構造化して残す（DAMAGE 等の
    state 形式でない効果では空タプル）。
    """

    kind: AppliedEffectKind
    visibility: EffectVisibility
    description: str
    target_ref: str = ""
    state_delta: Tuple[StateDeltaEntry, ...] = ()
