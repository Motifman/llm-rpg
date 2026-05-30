from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Tuple

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
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
    """接続の通行可否が変化した。

    ``cause`` は変化の発生原因 (Issue #180)。structured metadata として保持し、
    formatter / 観測モデルが「何の仕組みで変わったか」を機械可読に参照する。
    prose には焼き込まない (それは観測者の位置情報を反映する軸 3 の仕事)。

    ``original_actor_entity_id`` は連鎖の起点となった actor を追跡する
    (Issue #183, 軸 1+4)。``ACTOR_ACTION`` 由来なら actor の EntityId、
    ``REACTIVE`` / ``SCENARIO_EVENT`` のような世界 tick 由来は ``None``。
    観測者が actor と同 spot に居て視認可能な場合のみ、formatter / prompt
    builder 側でこの ID を使って「誰の行動だったか」を組み立てる。
    """

    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    traversable: bool
    cause: PassageChangeCauseEnum = PassageChangeCauseEnum.UNKNOWN
    original_actor_entity_id: Optional[EntityId] = None


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
class PlayerDroppedItemEvent(BaseDomainEvent[SpotGraphId, str]):
    """プレイヤーがインベントリから現在地の地面にアイテムを置いた。

    SpotGraphItemTransferService.drop_item() から発火される。観測パイプライン
    では「行為者を除く、同じスポットに居る全プレイヤー」に
    「Xが流木を地面に置いた」のような prose で配信される (witness 最小実装)。
    別スポットには伝わらない。行為者本人にはツール結果として
    ItemTransferResult.messages が返るので、観測ストリームには流さない (二重
    配信回避)。

    item_name は emission 時点で解決した表示名 (例: "流木")。観測 prose を
    formatter に運ぶための baked-in 値で、SpotObjectInteractedEvent の
    result_message と同じパターン。emission 後にアイテムスペックが renamed
    された場合でも、観測としての記録は当時の名前で保たれる。
    """

    entity_id: EntityId
    spot_id: SpotId
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    item_name: str


@dataclass(frozen=True)
class PlayerPickedUpItemEvent(BaseDomainEvent[SpotGraphId, str]):
    """プレイヤーが現在地の地面アイテムを拾い上げてインベントリに加えた。

    PlayerDroppedItemEvent と対称な配信仕様。「Xが流木を拾い上げた」のような
    prose で同室の他プレイヤーに観測として配信される。
    """

    entity_id: EntityId
    spot_id: SpotId
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    item_name: str


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


# Phase 4-O A: CHASE を諦める理由を表す Literal 型。formatter / handler /
# test 全箇所で同じ型を共有することで typo を静的に検出可能にする。
AbandonChaseReason = Literal[
    "grace_expired",        # CHASE 中に flee_grace_ticks (被弾以来の反応 tick) が切れた
    "max_ticks_exceeded",   # CHASE 累積 tick が chase_max_ticks を超えた
    "target_lost",          # last_observed_target_spot_id が無く、target も graph 上に居ない
    "search_expired",       # 探索フェーズの search_timer が満了 / chase_search_ticks=0
    "no_path",              # passable な経路が無い (target / last_observed への到達不可)
]


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

    def __post_init__(self) -> None:
        # discriminated union: 両方 None / 両方 non-None は不整合。
        # event 生成時点で弾く (formatter の防御 fallback には頼らない)。
        both_none = (
            self.target_player_id is None and self.target_monster_id is None
        )
        both_set = (
            self.target_player_id is not None
            and self.target_monster_id is not None
        )
        if both_none or both_set:
            raise ValueError(
                "MonsterStartedChasingInSpotEvent: target_player_id と "
                "target_monster_id は片方だけ非 None である必要がある "
                f"(player={self.target_player_id}, monster={self.target_monster_id})"
            )


@dataclass(frozen=True)
class MonsterAbandonedChaseInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが CHASE を諦めて IDLE に戻った (Phase 4a / 4b)。

    `reason` の許容値は `AbandonChaseReason` Literal で定義 (FLEE の grace
    切れではなく、CHASE 中の grace_expired / max_ticks / target_lost /
    search_expired / no_path のいずれか)。FLEE の grace 切れ (FLEE → IDLE
    の自然消滅) は本 event を発火しない (FLEE 終了用の専用 event 無し、
    既存 wander の MonsterLeft/Appeared で表現)。

    観測としては同 spot 全員に environment カテゴリで届く。「相手が諦めて
    去っていった」prose を組み立てられる。CHASE 諦めの直後に通常 wander
    に切り替わるので、後続の MonsterLeft/Appeared は「諦めて去った」と
    prose を読み変える文脈になる。
    """

    monster_id: MonsterId
    spot_id: SpotId
    reason: AbandonChaseReason


# Phase 4-O B: 環境温度による不快の種別は monster_enum.py に定義された
# TemperatureDiscomfortKind を共有する (template / event / formatter で
# 同じ Literal 型を使う)。
from ai_rpg_world.domain.monster.enum.monster_enum import (
    TemperatureDiscomfortKind,
)


@dataclass(frozen=True)
class MonsterFeltTemperatureDiscomfortInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """モンスターが spot の温度で不快を受けた瞬間 (Phase 4-O B)。

    `MonsterTemplate.min/max_comfortable_temperature` の範囲外の spot に
    居る間、`temperature_discomfort_damage_per_tick > 0` なら毎 tick HP が
    削られる。本 event はその度に発火する観測信号。

    `kind` で寒さ / 暑さを区別し、formatter で「身を震わせている」
    「弱っている」等の prose を切り替える。`damage_dealt` は実際に減った
    HP (clamping 等で template 値より小さくなる場合あり)。

    観測としては同 spot 全員に environment カテゴリで届く。
    """

    monster_id: MonsterId
    spot_id: SpotId
    kind: TemperatureDiscomfortKind
    damage_dealt: int


@dataclass(frozen=True)
class MonsterRespondedToPackHelpInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """pack member が仲間の救援要請に応答して CHASE 状態に入った瞬間
    (Phase 4-O C)。

    `responder_monster_id` が `victim_monster_id` の援護として CHASE に
    入ったことを示す。target は victim を殴った相手 (player or monster) で、
    `target_player_id` / `target_monster_id` のいずれかが設定される。

    観測としては responder の現在 spot 全員に environment カテゴリで届く。
    プレイヤーが仲間の monster を 1 匹殴ったとき「隣の spot から仲間が
    駆け付けてきた」prose を組み立てられる。

    `responder_spot_id` は responder の現在位置。CHASE で次 tick から
    target spot に向かって移動する。
    """

    responder_monster_id: MonsterId
    victim_monster_id: MonsterId
    responder_spot_id: SpotId
    # spot_id は base イベントとしての一貫性のため responder_spot_id と同じ
    # 値を持たせる (recipient strategy が `event.spot_id` を見て解決する規約)。
    spot_id: SpotId
    target_player_id: Optional[EntityId] = None
    target_monster_id: Optional[MonsterId] = None

    def __post_init__(self) -> None:
        # discriminated union: target は片方だけ非 None。
        both_none = (
            self.target_player_id is None and self.target_monster_id is None
        )
        both_set = (
            self.target_player_id is not None
            and self.target_monster_id is not None
        )
        if both_none or both_set:
            raise ValueError(
                "MonsterRespondedToPackHelpInSpotEvent: target_player_id と "
                "target_monster_id は片方だけ非 None である必要がある "
                f"(player={self.target_player_id}, monster={self.target_monster_id})"
            )


@dataclass(frozen=True)
class MonsterFollowedPackFleeInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """pack leader の FLEE に follower が追従して FLEE 状態に入った瞬間
    (Phase 4-O C #2)。

    leader 自身が FLEE に入る瞬間は既存の `MonsterStartedFleeingInSpotEvent`
    で観測される。本 event は follower (= 同 pack の他 member) が「リーダー
    の恐怖に引っ張られて」連動 FLEE に入ったことを別経路として識別するため
    のもの。

    観測 prose で「リーダー恐怖 → 群れ崩壊」を表現できる:
    - leader: MonsterStartedFleeingInSpotEvent → 「リーダーが逃げ出した」
    - follower: 本 event → 「{follower} もリーダーに続いて逃げ出した」

    観測としては follower の現在 spot 全員に environment カテゴリで届く。
    """

    follower_monster_id: MonsterId
    leader_monster_id: MonsterId
    follower_spot_id: SpotId
    # spot_id は recipient strategy 規約のため follower_spot_id と同じ値。
    spot_id: SpotId


@dataclass(frozen=True)
class MonsterAlertedByPackInSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """pack 警戒共有: scout が target を見つけて CHASE 中なのを察知して、
    近くの仲間が同じ target を CHASE 開始した瞬間 (Phase 4-O C #3)。

    `responder_monster_id` が `scout_monster_id` の警戒情報を受け取って
    CHASE に入ったことを示す。target は scout の `chase_attacker_ref` を
    そのまま継承する (player or monster の discriminated union)。

    pack 援護 (`MonsterRespondedToPackHelpInSpotEvent`) との違い:
    - 援護は「殴られた仲間」を契機 (`victim` 概念あり)
    - 警戒共有は「target を見つけた scout」を契機 (殴られていなくても発動)
    - prose の文脈も異なる: 援護は「救援に駆け付ける」、警戒共有は
      「警戒モードに入る」「気配を察する」

    観測としては responder の現在 spot 全員に environment カテゴリで届く。
    """

    responder_monster_id: MonsterId
    scout_monster_id: MonsterId
    responder_spot_id: SpotId
    # spot_id は recipient strategy 規約のため responder_spot_id と同じ値。
    spot_id: SpotId
    target_player_id: Optional[EntityId] = None
    target_monster_id: Optional[MonsterId] = None

    def __post_init__(self) -> None:
        # discriminated union: target は片方だけ非 None。
        both_none = (
            self.target_player_id is None and self.target_monster_id is None
        )
        both_set = (
            self.target_player_id is not None
            and self.target_monster_id is not None
        )
        if both_none or both_set:
            raise ValueError(
                "MonsterAlertedByPackInSpotEvent: target_player_id と "
                "target_monster_id は片方だけ非 None である必要がある "
                f"(player={self.target_player_id}, monster={self.target_monster_id})"
            )


# Phase 5: SpotSoundHeardEvent.intensity の許容値。
# SILENT は event 自体が発火しない (音なしで観測不要) ので除外。
# SoundIntensityEnum と同じ文字列値を共有することで、event 経由でも
# enum.value で値を統一できる。typo を静的に検出可能にするための Literal。
AudibleSoundIntensity = Literal["FAINT", "MODERATE", "LOUD"]


@dataclass(frozen=True)
class SpotSoundHeardEvent(BaseDomainEvent[SpotGraphId, str]):
    """spot に居る entity が環境音を聞いた (Phase 5 五感観察)。

    spot 入場時 / 「耳を澄ます」ツール実行時など、`SpotAtmosphere.sound_intensity`
    が SILENT より大きい spot に entity が居る場合に発火する。

    `intensity` は減衰後の強度。spot 入場 (= 自分が居る spot) では
    spot の sound_intensity そのもの。「耳を澄ます」ツール経由で隣接 spot
    の音を聞く場合は 1 hop 分減衰した値が入る (PR-2)。SILENT 相当 (減衰
    しきって聞こえない) は呼び出し側で event 発火を抑制すること。

    `source_spot_id` は音の発生源 spot で、`spot_id` (= entity が居る spot)
    と異なる場合がある (隣接 spot の音を聞いた時)。同じ spot なら両者一致。

    `ambient_description` は人間向けの自由記述 (例: 「川のせせらぎ」)。
    sound_ambient が None の spot では None。

    `entity_id` は常に player の ID を想定 (`PlayerId.value` と整合する
    整数空間)。monster の `EntityId` を渡した場合、observer pipeline で
    recipient が空になり観測として消費されない。
    """

    entity_id: EntityId
    # 観測者が居る spot (recipient 解決用、base event の規約)
    spot_id: SpotId
    # 音の発生源 spot (隣接 spot からの音だと spot_id と異なる)
    source_spot_id: SpotId
    intensity: AudibleSoundIntensity
    ambient_description: Optional[str] = None
