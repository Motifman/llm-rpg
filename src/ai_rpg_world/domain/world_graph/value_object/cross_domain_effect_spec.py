"""WorldGraphEffectResult に載せるクロスドメイン効果の指示。

ドメイン間の疎結合を保つため、world_graph ドメインは combat/player ドメインの
型に直接依存しない。代わりに文字列ベースの spec を出力し、
application 層が PlayerStatusAggregate 等へ適用する。

各 spec は `visibility` を持ち、効果が誰に観測可能かを示す
（行為者のツール結果に直接返す / 同スポットの第三者に観測として届く /
誰にも観測されない）。型ごとのデフォルトは「acting 側を直接変えるものは
ACTOR_DIRECT、環境や接続の物理変化は PUBLIC_OBSERVABLE」。
シナリオ側で上書きしたい場合は `visibility` を明示的に渡す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.value_object.passage import Passage


@dataclass(frozen=True)
class DamageSpec:
    damage: int
    message: str = ""
    visibility: EffectVisibility = EffectVisibility.ACTOR_DIRECT


@dataclass(frozen=True)
class StatusEffectSpec:
    effect_type_name: str  # "POISON", "PARALYSIS" 等
    value: float
    duration_ticks: int
    visibility: EffectVisibility = EffectVisibility.ACTOR_DIRECT


@dataclass(frozen=True)
class TeleportSpec:
    """接続を辿らない移動と、その移動が観測されるときの文面。

    文面をシナリオの宣言として持つのは、通気口・隠し通路・魔法陣が「接続を辿らない
    移動」という同じ仕組みの別名でしかないため。engine が action 名や語彙を知ると、
    新しい言い換えのたびに engine を触ることになる。

    出発 spot と到着 spot は明るさが違いうるので、文面は 4 つに分かれる。どれを
    選ぶかは**それぞれの spot の実効照明**で実行時に決める。未指定 (None) なら
    移動の既定文 (「Xがこのスポットを去った。」等) がそのまま出る。
    """

    target_spot_id: int
    visibility: EffectVisibility = EffectVisibility.ACTOR_DIRECT
    departure_observation_message: Optional[str] = None
    departure_observation_message_in_dark: Optional[str] = None
    arrival_observation_message: Optional[str] = None
    arrival_observation_message_in_dark: Optional[str] = None


@dataclass(frozen=True)
class AtmosphereUpdateSpec:
    spot_id: int
    lighting: Optional[str] = None
    temperature: Optional[str] = None
    hazard_level: Optional[int] = None
    hazard_description: Optional[str] = None
    visibility: EffectVisibility = EffectVisibility.PUBLIC_OBSERVABLE


@dataclass(frozen=True)
class CreateConnectionSpec:
    from_spot_id: int
    to_spot_id: int
    connection_name: str
    description: str = ""
    travel_ticks: int = 1
    is_bidirectional: bool = False
    passage: Passage = field(default_factory=Passage.open)
    visibility: EffectVisibility = EffectVisibility.PUBLIC_OBSERVABLE


@dataclass(frozen=True)
class DestroyConnectionSpec:
    connection_id: int
    visibility: EffectVisibility = EffectVisibility.PUBLIC_OBSERVABLE


@dataclass(frozen=True)
class SatisfyNeedSpec:
    need_type_name: str  # "HUNGER", "FATIGUE" 等
    amount: int
    visibility: EffectVisibility = EffectVisibility.ACTOR_DIRECT


@dataclass(frozen=True)
class DepositGoldSpec:
    """行為者の gold を減らして物へ納める。

    支払いは application 層が status 集約へ適用する。効果の適用中に
    所持金が足りない事態を作らないため、この効果を持つ interaction は
    読み込み時に PLAYER_GOLD_AT_LEAST の前提条件とペアであることを
    強制される。
    """

    amount: int
    visibility: EffectVisibility = EffectVisibility.ACTOR_DIRECT


@dataclass(frozen=True)
class PassageStateUpdateSpec:
    """接続の Passage を新しい状態へ遷移させる指示。

    application 層が `SpotGraphAggregate.set_connection_passage_state` を
    呼び出して反映する。`traversable_override` / `sound_permeability_override`
    を指定すると、kind+new_state の既定値を上書きできる。
    """

    connection_id: int
    new_state: str  # 対象接続の passage.kind に対応する状態文字列
    traversable_override: Optional[bool] = None
    sound_permeability_override: Optional[float] = None
    visibility: EffectVisibility = EffectVisibility.PUBLIC_OBSERVABLE


@dataclass(frozen=True)
class RoomOccupancyDisplaySpec:
    """世界全体の在室数を application 層で実行時に解決する指示。"""

    scope: str = "living_players_and_fallen_bodies"
    visibility: EffectVisibility = EffectVisibility.ACTOR_DIRECT
