from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional, Tuple, Mapping

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    StateDeltaEntry,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


@dataclass(frozen=True)
class EntityEnteredSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがスポットに入った

    ``observation_message`` は接続を辿らない移動 (``TELEPORT_ENTITY``) で
    シナリオが宣言した到着の文面。**既定文の差し替え**であって追加ではない。
    別イベントで足すと同じ移動が 2 回観測される。未指定なら従来の
    「Xが〜にやってきた。」が使われる。
    """

    entity_id: EntityId
    spot_id: SpotId
    from_spot_id: Optional[SpotId]
    observation_message: Optional[str] = None


@dataclass(frozen=True)
class EntityLeftSpotEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがスポットを離れた

    ``observation_message`` は ``EntityEnteredSpotEvent`` と対で、出発側の
    文面を宣言から差し替える。
    """

    entity_id: EntityId
    spot_id: SpotId
    to_spot_id: SpotId
    observation_message: Optional[str] = None


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
    # 著者が書いた日本語の観測テキスト。formatter は narrative がある時だけ
    # observation を emit する (None なら silent = 内部用語の漏洩を防ぐ)。
    # 旧コードは state_delta から "available が False から True に変わった"
    # を機械生成してプロンプトに垂れ流していた (#356 後続 finding)。
    narrative: Optional[str] = None


@dataclass(frozen=True)
class SpotObjectInteractedEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがオブジェクトと相互作用した。

    Phase G #1: `witness_policy` フィールドで配信範囲を制御する。
    - SAME_SPOT (デフォルト): 同 spot の他プレイヤーが観測 (既存挙動)
    - ACTOR_ONLY: 行為者本人だけ (PlayerDroppedItemEvent と同じ pattern)
    """

    entity_id: EntityId
    spot_id: SpotId
    object_id: SpotObjectId
    action_name: str
    result_message: str
    # InteractionDef.display_label 由来の行動表示。目撃者向け文面が無い場合の
    # prose fallback にだけ使う。本人向け result_message とは分離する。
    action_display_label: str = ""
    # InteractionDef.witness_observation_message 由来の目撃者専用 prose template。
    # result_message のような「本人が得た中身」はここへ載せない。
    witness_observation_message: str = ""
    # Phase G #1: 観測配信範囲。InteractionDef.witness_policy から伝搬する。
    # default SAME_SPOT で後方互換 (既存 caller は kw 引数を省略できる)。
    witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT


@dataclass(frozen=True)
class PlayerInteractedWithPlayerEvent(BaseDomainEvent[SpotGraphId, str]):
    """プレイヤーが、同じ場所にいる別のプレイヤーを対象に行為を行った。

    ``SpotObjectInteractedEvent`` の対人版。物体版と分けているのは、
    ``ObservedEventRegistry`` が型の完全一致で strategy を引くためと、
    目撃者向けの prose に「対象が誰か」が要るため。

    観測を伴わない対人行為は作らない。state だけ変わって誰にも何も見えない
    と、被害者は次のターンに持ち物が消えていることに気づくだけになり、
    trace からも効果を確認できない (agent_design_principles.md
    「他者からの可視性」)。

    ``witness_policy`` は物体版と同じ意味。秘匿して奪う行為を書けるように
    ACTOR_ONLY も選べる。
    """

    entity_id: EntityId
    target_entity_id: EntityId
    spot_id: SpotId
    action_name: str
    result_message: str
    # InteractionDef.display_label 由来。目撃者向け文面が無いときの fallback。
    action_display_label: str = ""
    # InteractionDef.witness_observation_message 由来の目撃者専用 prose。
    witness_observation_message: str = ""
    witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT
    # **行為が始まった時点で**対象が倒れていたか。
    #
    # 「いま倒れているか」を後から集約に問い合わせると、対象を昏倒させた
    # 一撃そのものが「倒れている間にされたこと」に化ける (致死の一撃は必ず
    # そうなる)。倒された事実は PlayerDownedEvent 由来の観測で本人に即座に
    # 届くので、目覚めの申し送りにも入れると同じ一撃が二重に語られる。
    target_was_down: bool = False
    # InteractionDef.notify_target 由来。可視性の 3 軸目で、「対象本人に
    # 行為が届くか」だけを決める (第三者に届くかは witness_policy)。
    #
    # ACTOR_ONLY と組み合わせたときだけ配信先が変わる。SAME_SPOT では対象は
    # 既に「同スポットの他プレイヤー」として含まれている。
    notify_target: bool = False
    # InteractionDef.target_observation_message 由来の、対象本人にだけ見せる
    # prose。秘匿行為では「誰にやられたか」を伏せたいことがあるので、目撃者
    # 向け文面とは別に書けるようにする。
    target_observation_message: str = ""


@dataclass(frozen=True)
class GamePhaseChangedEvent(BaseDomainEvent[SpotGraphId, str]):
    """世界のモード (自由時間 / 会議) が切り替わった。

    **世界全体のイベント**なので、場所を問わず全プレイヤーに配信する
    (``TimeOfDayChangedEvent`` と同じ扱い)。会議が始まったことが届かない
    プレイヤーが居ると、その人は会議に参加できないまま議論が進む。

    ``initiator_display_name`` を載せるのは、**誰が招集したか自体が推理の
    材料になる**ため。緊急ボタンを押した人は疑いの的にも信頼の的にもなる。
    世界が勝手に始めた遷移 (沈黙による終了など) では空文字にする。
    """

    old_phase: GamePhase
    new_phase: GamePhase
    #: この遷移の理由。招集なら ``emergency_button`` / ``body_report``、
    #: 会議の終了なら ``vote_concluded`` / ``silence`` / ``tick_limit``。
    trigger: str = ""
    #: 招集した人の表示名。世界都合の遷移では空。
    initiator_display_name: str = ""


@dataclass(frozen=True)
class MeetingVoteResolvedEvent(BaseDomainEvent[SpotGraphId, str]):
    """会議の投票が締め切られ、集計が出た。

    **追放の有無にかかわらず発火する。** 同点や棄権最多では世界に何も起き
    ないのでドメインイベントが自然には出ず、この経路は実装から漏れる
    (設計 doc §6.4)。漏れると「誰も追放されなかった」のか「誰かが追放された
    が自分は見ていなかった」のかを区別できない。

    誰が誰に入れたかまで載せるのは、**投票行動そのものが次の会議の材料に
    なる**ため。集計だけにすると社会的推論の材料が一段減る。

    名前で持つのは、観測が prompt にそのまま出る文だから。id を載せても
    受け手が解決できない。
    """

    #: 追放された人の表示名。誰も追放されなければ空。
    ejected_display_name: str = ""
    #: この集計で実際にoutcomeがEJECTEDへ遷移したplayer。通知順制御に使う。
    ejected_player_id: Optional[PlayerId] = None
    #: 指名された人ごとの得票数。
    counts_by_display_name: Mapping[str, int] = field(default_factory=dict)
    #: 棄権の数。
    skip_count: int = 0
    #: 投票者 -> 投票先 (棄権は空文字)。
    ballots_by_display_name: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MeetingVoteCastEvent(BaseDomainEvent[SpotGraphId, str]):
    """会議中に 1 人が投票を済ませた。

    締切前に公開してよいのは投票者と残り人数だけである。投票先をイベントに
    持たせないことで、formatter や trace の別経路から漏れる余地を作らない。
    """

    voter_player_id: PlayerId
    voter_display_name: str = ""
    remaining_voter_count: int = 0


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
    # Phase C: 観測範囲。SAME_SPOT (default) なら同スポット他プレイヤーに配信、
    # ACTOR_ONLY なら recipient strategy が空集合を返し誰も観測しない。
    # default は SAME_SPOT で B-2a までの挙動と一致 (後方互換)。
    witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT


@dataclass(frozen=True)
class PlayerOverflowedItemEvent(BaseDomainEvent[SpotGraphId, str]):
    """持ちきれなかった品が、その人の足元に落ちた。

    **意図して置いた (`PlayerDroppedItemEvent`) とは別の出来事**として扱う。
    地面に物が増えるのは同じでも、**拾ってよいかの読みが変わる**。置いたものは
    誰かのための置き方かもしれないが、取り落としたものは本人が拾い直したいはず
    で、そこを潰すと親切のつもりの持ち去りが増える。

    配信先も違う。置いた側は自分の行動なので本人へは流さないが、取り落としは
    **本人が知らないと拾い直せない**。採取の結果が手元に無い理由が、本人には
    ここでしか分からない。
    """

    entity_id: EntityId
    spot_id: SpotId
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    item_name: str


@dataclass(frozen=True)
class MarketDeliveryLeftAtBoardEvent(BaseDomainEvent[SpotGraphId, str]):
    """買い注文で届いた品を受け取れず、掲示板の足元に置かれた。

    **取り落とし (`PlayerOverflowedItemEvent`) とは別の出来事**にする。落ちた
    のは本人の不注意ではなく、**届いた品を受け取れなかった**ためで、そこを
    混ぜると読み違える。

    置かれるのは常に板の前で、買い手の居場所には依存しない。買い手が板から
    離れていても届ける — gold は減っているのに品が無い理由が、本人には
    ここでしか分からない。
    """

    entity_id: EntityId
    spot_id: SpotId
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    item_name: str


@dataclass(frozen=True)
class TimeOfDayChangedEvent(BaseDomainEvent[SpotGraphId, str]):
    """昼夜サイクルのフェーズが変化した (例: 昼 → 夕暮れ)。

    SpotGraphDayNightStageService から発火される全プレイヤー向け observation
    event。屋外 / 屋内の区別は本イベントには持たせず (実情、屋内でも空の色や
    肌寒さで時間経過は感じられる)、recipient strategy で全プレイヤーへ届ける
    シンプルな仕様にする。

    シナリオが `day_night.announce_changes: false` を設定している場合は、
    本イベント自体を発火させない (callback を登録しない経路で抑止する)。
    """

    old_phase_name: str
    new_phase_name: str
    new_display_text: str
    new_is_dark: bool


@dataclass(frozen=True)
class PlayerGaveItemEvent(BaseDomainEvent[SpotGraphId, str]):
    """プレイヤーが同室の別プレイヤーへアイテムを直接渡した。

    SpotGraphItemTransferService.give_item() から発火される。観測パイプライン
    では「行為者 (送り手) を除く、同じスポットに居る全プレイヤー」に配信される。
    受取り側 (recipient_entity_id) もこの集合に含まれるため「Xが流木をYに渡した」
    という観測を受け取る (本人視点でも prose は三人称的になる、これは仕様)。
    送り手本人にはツール結果として messages が返るため観測ストリームには
    流さない (二重配信回避)。
    """

    entity_id: EntityId
    recipient_entity_id: EntityId
    spot_id: SpotId
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    item_name: str


@dataclass(frozen=True)
class PlayerTradeOfferEvent(BaseDomainEvent[SpotGraphId, str]):
    """エージェント同士の取引が動いた (経済統合 Phase 2)。

    持ちかけ・成立・辞退・期限切れを 1 つのイベントにまとめ、``kind`` で
    分ける。読む側 (観測の文面、trace の集計) はどれも「誰が・誰と・何と何を」
    を同じ形で読むので、4 つに割ると読む側が 4 経路を覚えることになる。

    配信先は kind で変わる。持ちかけと成立は**その場の第三者にも**見える
    (中身つき)。辞退と期限切れは当事者だけに届く — 断りや沈黙まで公開すると、
    観測が increases するばりに交渉の緊張が薄まる。
    """

    entity_id: EntityId
    partner_entity_id: EntityId
    spot_id: SpotId
    #: ``offered`` / ``accepted`` / ``declined`` / ``expired``
    kind: str
    #: 持ちかけた側から見た「差し出すもの」「求めるもの」の説明文。
    gives_text: str
    asks_text: str
    #: 期限切れのときだけ、当事者それぞれへ別の文面を出すために使う。
    offerer_entity_id: Optional[EntityId] = None


@dataclass(frozen=True)
class MarketBoardActivityEvent(BaseDomainEvent[SpotGraphId, str]):
    """市場の掲示板の上で何かが動いた (経済統合 Phase 3)。

    出品・値の付け直し・約定・取り下げ・期限切れを 1 つのイベントにまとめ、
    ``kind`` で分ける。読む側はどれも「誰が・何を・いくつ・いくらで」を同じ
    形で読むので、5 つに割ると読む側が 5 経路を覚えることになる
    (Phase 2 の取引イベントと同じ判断)。

    配信先は kind で変わる。板の上の出来事 (出品・値の付け直し・約定・
    取り下げ) は**板の前に居る人**に見える。板は公開の場なので、そこで
    起きたことがその場に居る人に見えないのは不自然。

    ``notify_entity_id`` は**その場に居なくても届けたい相手**。板越しの
    取引では、売り手がその場に居ないまま自分の品が売れる。届けないと、次に
    板へ寄るまで自分の持ち物が変わった理由が分からない。期限切れも同じ。
    """

    entity_id: EntityId
    spot_id: SpotId
    #: ``listed`` / ``repriced`` / ``bought`` / ``cancelled`` /
    #: ``expired_returned`` / ``expired_awaiting``
    kind: str
    #: その注文の向き (``sell`` / ``buy``)。同じ ``kind`` でも、売り注文を
    #: 出したのか買い注文を出したのかで文面が変わる。
    side: str
    item_name: str
    quantity: int
    unit_price: int
    #: 値の付け直しのときの、変更前の単価。方向 (下げた / 上げた) を読むため。
    old_unit_price: Optional[int] = None
    #: 約定のときの相手 (売り手)。誰の値が受け入れられたかを見せるために要る。
    counterparty_entity_id: Optional[EntityId] = None
    #: 同席していなくても届ける相手 (売れた売り手 / 流れた注文の持ち主)。
    notify_entity_id: Optional[EntityId] = None


@dataclass(frozen=True)
class PlayerTradedWithMerchantEvent(BaseDomainEvent[SpotGraphId, str]):
    """プレイヤーが同席する NPC 商人と売り買いした (経済統合 Phase 1)。

    買いと売りを 1 つのイベントにまとめ、``direction`` で分ける。集計する側
    (trace の gold 流量、観測の文面) はどちらも「誰が・誰と・何を・いくつ」を
    同じ形で読むので、2 つに割ると読む側が 2 経路を覚えることになる。

    配信は同席の第三者だけ (行為者はツール結果で知る)。``schedules_turn`` は
    立てない — 相手は NPC で起こす手番が無く、第三者にとっても「隣で誰かが
    買い物をした」は自分の次の一手を変えない。
    """

    entity_id: EntityId
    spot_id: SpotId
    merchant_name: str
    item_name: str
    item_spec_id: ItemSpecId
    quantity: int
    #: ``merchant_buy`` / ``merchant_sell``。
    direction: str


@dataclass(frozen=True)
class PlayerPickedUpItemEvent(BaseDomainEvent[SpotGraphId, str]):
    """プレイヤーが現在地の地面アイテムを拾い上げてインベントリに加えた。

    PlayerDroppedItemEvent と対称な配信仕様。「Xが流木を拾い上げた」のような
    prose で同室の他プレイヤーに観測として配信される。

    witness_policy=ACTOR_ONLY のときは「こっそり拾う」を表現し、recipient
    strategy が空集合を返すため誰にも観測されない。
    """

    entity_id: EntityId
    spot_id: SpotId
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    item_name: str
    witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT


@dataclass(frozen=True)
class SpotObjectInteractionFailedEvent(BaseDomainEvent[SpotGraphId, str]):
    """エンティティがオブジェクト操作を試みたが前提条件で失敗した。

    観測としては「アクター本人ではない、同じスポットの他プレイヤー」に
    配信される。アクター本人には別途ツール結果として `failure_message` が
    返る（重複しないようにここでは除外）。

    prose の決まり方 (formatter で評価):
    1. `observation_message` が空でない → そのまま prose に使う (シナリオ
       作家が `on_failure_observation` で宣言した override)
    2. それも空で `failure_reason` がある → 「{actor}が{object}の{action}を
       試みたが、{reason}」を formatter が自動構築する (#356 後続:
       他者の失敗から学べるようにする)
    3. 両方空 → 観測非発火 (legacy fallback、レガシー emit 経路用)
    """

    entity_id: EntityId
    spot_id: SpotId
    object_id: SpotObjectId
    action_name: str
    observation_message: str
    # #356 後続: domain 例外の reason をそのまま運ぶ。formatter が他者向け
    # prose の自動構築に使う。None / 空文字なら自動構築しない。
    failure_reason: Optional[str] = None
    # シナリオが書いた表示名。**目撃文にはこちらを使う。**
    #
    # action_name は engine の識別子で、人が口にする言葉ではない。さらに
    # 秘匿役職のシナリオでは偽装版の識別子 (`..._pretend`) がそのまま漏れる。
    # 本物と偽装は同じ display_label を持つので、ラベルで書けば失敗文も
    # 見分けがつかなくなる。
    display_label: str = ""


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


@dataclass(frozen=True)
class SpotPresenceListenedEvent(BaseDomainEvent[SpotGraphId, str]):
    """耳を澄ませた entity が隣接 spot の人の気配を捉えた。

    ``moving_occupants`` は音の通りやすさに応じて情報量を落とす。
    ``hops == 1`` では 0 以上の人数、``hops == 2`` では不在なら 0、
    誰か居れば人数を伏せるため ``None``、``hops >= 3`` では在否を
    区別せず常に ``None`` とする。文面は観測 formatter が組み立てる。
    """

    entity_id: EntityId
    spot_id: SpotId
    source_spot_id: SpotId
    hops: int
    moving_occupants: Optional[int]
