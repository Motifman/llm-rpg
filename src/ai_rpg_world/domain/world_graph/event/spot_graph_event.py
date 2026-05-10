from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
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

    Field naming は `PlayerAttackedMonsterInSpotEvent` と対称（Phase B 統合）:
    - `attacker_monster_id` ↔ `attacker_entity_id`（攻撃者）
    - `target_player_id` ↔ `target_monster_id`（対象）
    - `target_incapacitated`（共通: PlayerDowned / MonsterDead）
    """

    attacker_monster_id: MonsterId
    spot_id: SpotId
    target_player_id: EntityId
    damage: int
    target_incapacitated: bool
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


@dataclass(frozen=True)
class PlayerAttackedMonsterInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """プレイヤーが同スポットのモンスターに攻撃を行った。

    観測としては行為者プレイヤーを除く同スポット全員に social カテゴリで届く。
    行為者本人にはツール結果として個別メッセージが返るので除外する
    （二重観測防止 / `MonsterAttackedPlayerInSpotEvent` の actor 側ガードと対称）。

    `MonsterDamagedEvent` / `MonsterDiedEvent` は monster aggregate 側で自動
    発火するが、それらは "monster" 戦略の別観測経路。本 event は spot graph
    視点での「誰が誰を殴ったか」の prose 構築を担う。

    `target_incapacitated` は致命攻撃で `MonsterStatusEnum.DEAD` に遷移した
    ことを意味する。観測 prose に「倒した」suffix を付けるために使う。
    `MonsterAttackedPlayerInSpotEvent.target_incapacitated`（PlayerDowned）と
    同じ field 名を採用し、両 event を対称化する（Phase B 統合）。

    Field naming は `MonsterAttackedPlayerInSpotEvent` と対称:
    - `attacker_entity_id` ↔ `attacker_monster_id`（攻撃者）
    - `target_monster_id` ↔ `target_player_id`（対象）
    - `target_incapacitated`（共通）
    """

    attacker_entity_id: EntityId
    target_monster_id: MonsterId
    spot_id: SpotId
    damage: int
    target_incapacitated: bool


@dataclass(frozen=True)
class MonsterAteGroundItemEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが地面のアイテムを食べた（採食）。

    Phase 3a: 飢餓 tick で hunger が `forage_threshold` 以上に達したモンスターが、
    同スポットの地面アイテムのうち `template.preferred_feed_item_spec_ids` に
    含まれる種別を 1 つ消費したときに発火する。

    観測としては同スポットの全プレイヤーに social カテゴリで届く。actor は
    monster なので self 除外は不要。

    `item_spec_id` は formatter で名前解決のために使う。`item_instance_id` は
    structured 出力やログ照会向け（同種別が複数置かれている時の追跡用）。
    """

    monster_id: MonsterId
    spot_id: SpotId
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId


@dataclass(frozen=True)
class MonsterPredatedMonsterInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが同スポットの prey モンスターを攻撃した（捕食）。

    Phase 3b: hungry な捕食者が `template.prey_races` にマッチする生存
    モンスターを攻撃したときに発火。多 tick 戦闘（モデル B）なので 1 撃で
    必ずしも仕留めるわけではなく、`target_killed` で致命攻撃かを示す。

    Field naming は `MonsterAttackedPlayerInSpotEvent` /
    `PlayerAttackedMonsterInSpotEvent` と同じ規約:
    - `attacker_monster_id`: 狩る側
    - `target_monster_id`: 狩られる側
    - `target_incapacitated`: 致命攻撃で MonsterDead に遷移したか
      （hunger 回復はこの値が True のときに発生）

    観測としては同 spot 全プレイヤーに social として届く。actor/target が
    どちらも monster なので player の self 除外は不要。

    Phase 4 (反撃 / 逃走) では prey 側がこの event を購読して FLEE 状態に
    遷移する想定。
    """

    attacker_monster_id: MonsterId
    target_monster_id: MonsterId
    spot_id: SpotId
    damage: int
    target_incapacitated: bool


@dataclass(frozen=True)
class MonsterStartedFleeingInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが FLEE 状態に遷移した (Phase 4a)。

    被弾後、`reaction_to_attack` policy に従って FLEE 状態に入った瞬間に
    発火する。後続の `MonsterLeftSpotEvent` / `MonsterAppearedAtSpotEvent`
    と組み合わせると「殴られて慌てて逃げ出した」prose を組み立てられる。

    観測としては同 spot 全員に environment カテゴリで届く。被害者プレイヤー
    本人を含めて「相手が逃げ出した」が見える。

    Phase 4a: 状態遷移時の 1 回だけ発火。FLEE 中の毎 tick の wander は
    既存の MonsterLeft/MonsterAppeared で表現する。
    """

    monster_id: MonsterId
    spot_id: SpotId


@dataclass(frozen=True)
class MonsterStartedChasingInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが CHASE 状態に遷移した (Phase 4a)。

    被弾後、`reaction_to_attack` policy が ALWAYS_RETALIATE 等で CHASE 状態
    に入った瞬間に発火する。target は player or monster なので 2 つの id
    フィールドを持ち、片方が NULL になる。

    観測としては同 spot 全員に environment カテゴリで届く。target である
    プレイヤー本人には「相手が襲いかかってくる」が見える。

    Phase 4a: 状態遷移時の 1 回だけ発火。CHASE 中の毎 tick の追跡移動は
    既存の MonsterLeft/MonsterAppeared で表現する。
    """

    monster_id: MonsterId
    spot_id: SpotId
    # target は player or monster の片方だけ非 None (discriminated union)。
    target_player_id: Optional[EntityId] = None
    target_monster_id: Optional[MonsterId] = None


@dataclass(frozen=True)
class MonsterAbandonedChaseInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが CHASE を諦めて IDLE に戻った (Phase 4a / 4b)。

    以下のいずれかの理由で `clear_behavior_state_to_idle()` を呼んだ瞬間に
    発火する:

    - `grace_expired`: `flee_grace_ticks` 経過 (被弾以来の反応 tick 切れ)
    - `max_ticks_exceeded`: `chase_max_ticks` 経過 (CHASE 累積 tick 切れ)
    - `target_lost`: target が graph 上に居なくなり、見失い → 探索 → IDLE
    - `no_path`: passable な経路が無い (target spot / last_observed への
      到達不可)
    - `search_expired`: `chase_search_ticks` 経過 (探索フェーズが完了)

    観測としては同 spot 全員に environment カテゴリで届く。「相手が諦めて
    去っていった」prose を組み立てられる。CHASE 諦めの直後に通常 wander
    に切り替わるので、後続の MonsterLeft/Appeared は「諦めて去った」と
    prose を読み変える文脈になる。
    """

    monster_id: MonsterId
    spot_id: SpotId
    reason: str
