from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    StateDeltaEntry,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


@dataclass(frozen=True)
class EntityEnteredSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがスポットに入った"""

    entity_id: EntityId
    spot_id: SpotId
    from_spot_id: Optional[SpotId]


@dataclass(frozen=True)
class EntityLeftSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがスポットを離れた"""

    entity_id: EntityId
    spot_id: SpotId
    to_spot_id: SpotId


@dataclass(frozen=True)
class ConnectionStateChangedEvent(BaseDomainEvent[SpotGraphId, str]):
    """接続の通行可否が変化した"""

    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    traversable: bool


@dataclass(frozen=True)
class EntityEnteredSubLocationEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがサブロケーションに入った"""

    entity_id: EntityId
    spot_id: SpotId
    sub_location_id: SubLocationId


@dataclass(frozen=True)
class SpotObjectStateChangedEvent(BaseDomainEvent[SpotGraphId, str]):
    """スポット内オブジェクトの状態が変化した。

    Phase 4-E: PUBLIC_OBSERVABLE な効果由来でこのイベントが発火する場合
    `actor_entity_id` を行為者の EntityId に設定する。受信者解決時に同
    プレイヤーは観測対象から除外される (二重観測防止)。世界 tick 等で
    発火する非アクター由来の場合は None。

    `state_delta` は formatter が「{key} が {before} から {after} に
    変わった」というテキストを構築するための構造化差分。effect 適用側で
    既に計算した `StateDeltaEntry` を渡す。空の場合 formatter は
    `old_state`/`new_state` から導出する。
    """

    spot_id: SpotId
    object_id: SpotObjectId
    old_state: Dict[str, Any]
    new_state: Dict[str, Any]
    actor_entity_id: Optional[EntityId] = None
    state_delta: Tuple[StateDeltaEntry, ...] = ()


@dataclass(frozen=True)
class SpotObjectInteractedEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがオブジェクトと相互作用した"""

    entity_id: EntityId
    spot_id: SpotId
    object_id: SpotObjectId
    action_name: str
    result_message: str


@dataclass(frozen=True)
class SpotObjectInteractionFailedEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがオブジェクト操作を試みたが前提条件で失敗した。

    観測としては「アクター本人ではない、同じスポットの他プレイヤー」に
    `observation_message` として配信される。アクター本人には別途ツール
    結果として `failure_message` が返る（重複しないようにここでは除外）。
    """

    entity_id: EntityId
    spot_id: SpotId
    object_id: SpotObjectId
    action_name: str
    observation_message: str


@dataclass(frozen=True)
class SpotPlayerPreparedActionEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティが prepare_action で同期アクションの準備をした。

    協力ギミック #13 の sync group に属する action_id が prepare された
    際に、同じスポットの他プレイヤーへ「相方が準備している」を観測として
    配信するためのイベント。`observation_message` はシナリオ作家が
    `SynchronizedActionGroup.on_prepare_observation_message` で指定。
    """

    entity_id: EntityId
    spot_id: SpotId
    action_id: str
    group_id: str
    observation_message: str


@dataclass(frozen=True)
class SpotExploredEvent(BaseDomainEvent[SpotGraphId, str]):
    """スポットが探索された"""

    entity_id: EntityId
    spot_id: SpotId
    discoveries: Tuple[str, ...]


@dataclass(frozen=True)
class ItemDiscoveredEvent(BaseDomainEvent[SpotGraphId, str]):
    """探索でアイテムが発見された"""

    entity_id: EntityId
    spot_id: SpotId
    item_spec_id: ItemSpecId


@dataclass(frozen=True)
class TrapTriggeredEvent(BaseDomainEvent[SpotGraphId, str]):
    """トラップが発動した"""

    entity_id: EntityId
    spot_id: SpotId
    trap_id: str
    messages: Tuple[str, ...]


@dataclass(frozen=True)
class ConnectionCreatedEvent(BaseDomainEvent[SpotGraphId, str]):
    """接続が動的に生成された"""

    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId


@dataclass(frozen=True)
class ConnectionDestroyedEvent(BaseDomainEvent[SpotGraphId, str]):
    """接続が動的に破壊された"""

    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId


@dataclass(frozen=True)
class SpotPlayerStateChangedInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """同スポット内のプレイヤーの公開可能な state が変化したことを第三者に伝える。

    Phase 4-E: `CHANGE_PLAYER_STATE` のような effect が `PUBLIC_OBSERVABLE`
    視認性で適用されたとき (例: 変装が解けた、姿勢が変わった、肉眼で
    分かる buff が乗った) に発火する。受信者解決は actor を除外した同
    スポット住人。本人は自分の state を current_state プロンプトで知る
    ため、観測としては流さない。

    内臓的な変化 (毒・呪い・隠しフラグ) はデフォルト HIDDEN なのでこの
    event は発火しない。
    """

    entity_id: EntityId
    spot_id: SpotId
    state_delta: Tuple[StateDeltaEntry, ...]
    observation_message: str = ""


@dataclass(frozen=True)
class SpotPublicEffectObservedEvent(BaseDomainEvent[SpotGraphId, str]):
    """専用 event が無い種類の `PUBLIC_OBSERVABLE` 効果サマリを汎用に運ぶ event。

    Phase 4-E PR 3: PR 1 で導入した `AppliedEffectSummary` のうち、
    SPOT_OBJECT_STATE_CHANGE と ACTING_PLAYER_STATE_CHANGE 以外の
    PUBLIC_OBSERVABLE な kind (DAMAGE / STATUS_EFFECT / SATISFY_NEED /
    ATMOSPHERE_UPDATE / TARGET_ITEM_STATE_CHANGE / ACTING_ITEM_STATE_CHANGE
    のうち PUBLIC 上書きされたもの) を、同スポットの第三者プレイヤーに
    観測として届けるための catch-all。

    formatter が `kind` で分岐して具体プロセを組み立てる。CONNECTION_*
    と PASSAGE_STATE_UPDATE は graph aggregate が個別 event を発火するため
    ここでは扱わない (重複発火防止)。TELEPORT は現状 spec 適用が未実装
    (dead code) のため emitter 側で skip する。

    `actor_entity_id` は二重観測防止のため受信者解決で行為者を除外する用。
    actor 不明 (世界 tick 由来) の場合は None を入れる (現状そのケースは無い)。
    """

    spot_id: SpotId
    actor_entity_id: Optional[EntityId]
    kind: AppliedEffectKind
    description: str
    target_ref: str
    state_delta: Tuple[StateDeltaEntry, ...]


@dataclass(frozen=True)
class MonsterAppearedAtSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスター個体がスポットに出現した（spawn / 配置）。

    ステップ1では「停止して居る」だけのライフサイクル開始イベント。
    将来 spawn 由来 (spawn_table) と動的配置 (デバッグ・スクリプト) を
    区別したくなったら `cause` 等のフィールドを足す方針。
    """

    monster_id: MonsterId
    spot_id: SpotId


@dataclass(frozen=True)
class MonsterAttackedPlayerInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが同スポットのプレイヤー 1 体を攻撃した。

    観測としては当該スポットの全プレイヤー（被害者本人を含む）に environment
    カテゴリで届く。攻撃者である monster は PlayerId と同一空間ではないので
    self 除外は不要。

    被害者本人にもツール結果ではなく観測として届ける（観測 push のみ）。
    プレイヤー側の HP 減少自体は PlayerStatusAggregate の `apply_damage` 経路
    で別 event (PlayerDownedEvent 等) を発火する想定で、本 event は「何が
    起きたか」の prose を組み立てる責任のみを持つ。

    `target_visible` が False の場合は被害者プレイヤーから「何かに襲われた」
    という暗闇 prose を出す前提（暗闇でも dark_vision モンスターは攻撃可能）。
    現状は recipient 側で全員に同じ prose を出すが、将来的には受信者ごとに
    視認可否で分岐させる余地がある。
    """

    monster_id: MonsterId
    spot_id: SpotId
    target_player_id: EntityId
    damage: int
    target_downed: bool
    # 被害者から見て monster が「視認できているか」。被害者プレイヤーが暗闇に
    # 居て attacker 側だけ dark_vision を持つケースでは False。最小実装では
    # 被害者の視認も effective_lighting で判定し、attacker 側との非対称も
    # 許容する。
    target_visible: bool


@dataclass(frozen=True)
class MonsterLeftSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスター個体がスポットから離れた（despawn / 死亡 / 撤去）。

    ステップ1では移動が無いため、用途は撤去・死亡などの「居なくなる」
    片道遷移。後続 PR で隣接スポットへの移動を実装する際は、Left →
    Appeared を対で発火するか、専用の MovedEvent を追加するかを決める。
    """

    monster_id: MonsterId
    spot_id: SpotId
