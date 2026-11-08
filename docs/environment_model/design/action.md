# 行為 (ActionAttempt)

```python
class ActionAttempt(Protocol):
    @property
    def actor(self) -> PersonId: ...
    def kind(self) -> ActionKind: ...
    def actor_requirement(self) -> ActorRequirement: ...
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]: ...
    def exertion(self) -> Exertion: ...
    def person_as(self, kind: SubjectKind) -> PersonId: ...   # 答えられない主語は SubjectNotInTriggerException
    def this_item(self) -> ItemInstanceId: ...                # 品物の無い行為は ItemNotInTriggerException


Trigger = ActionAttempt | HappeningFired | ReactionFired | GroupDecisionResult | JointActionCompleted | WorldTimePassing | EachPersonOf
# どのきっかけも person_as と this_item を持つ。GroupDecisionResult は CHOSEN_BY_GROUP だけを答え、ほかの行為でないきっかけは何も答えない

@final
@dataclass(frozen=True)
class EachPersonOf:                         # ForEveryone などの中で、外のきっかけと「その人」を包む
    outer: Trigger
    person: PersonId                        # EACH_PERSON にはこの人を、ほかの主語と品物は outer が答える

@final
@dataclass(frozen=True)
class JointActionCompleted:
    joint: CompletedJointAction             # joint_id を答える Protocol。JointActionDeclaration が満たす

@final
@dataclass(frozen=True)
class HappeningFired:
    happening: FiredHappening               # happening_id を答える Protocol。HappeningDeclaration が満たす

@final
@dataclass(frozen=True)
class ReactionFired:
    reaction: FiredReaction                 # reaction_id を答える Protocol。ReactionDeclaration が満たす

@final
@dataclass(frozen=True)
class GroupDecisionResult:
    decision: GroupDecisionDeclaration
    chosen: PersonId

@final
@dataclass(frozen=True)
class WorldTimePassing:                     # 時間が進んだことがきっかけ (PassWorldTime の中の空腹、死の猶予など)
    tick: WorldTick

ActorRequirement = LivingOnly | LivingOrDeparted
CopresenceRequirement = WithPerson | WithObject | WithGroundItem | WithMonster | WithMerchant | WithMarketBoard
Exertion = UsesBody | DoesNotUseBody

class ActionKind(Enum):                     # どの世界にもある行為の種類。作者の操作は InteractionId で指す
    TRAVEL = "TRAVEL"
    SPEAK = "SPEAK"
    LISTEN = "LISTEN"
    WAIT = "WAIT"
    TEND = "TEND"
    HAND_OVER = "HAND_OVER"
    PICK_UP = "PICK_UP"
    DROP = "DROP"
    SEARCH = "SEARCH"
    USE_ITEM = "USE_ITEM"
    ENTER_SECTION = "ENTER_SECTION"
    LEAVE_SECTION = "LEAVE_SECTION"
    HOLD = "HOLD"
    PUT_AWAY = "PUT_AWAY"
    CAST_BALLOT = "CAST_BALLOT"
    INTERACT_WITH_OBJECT = "INTERACT_WITH_OBJECT"
    INTERACT_WITH_CARRIED_ITEM = "INTERACT_WITH_CARRIED_ITEM"
    INTERACT_WITH_PERSON = "INTERACT_WITH_PERSON"
    ATTACK_MONSTER = "ATTACK_MONSTER"
    # 取引と市場の種類は、その宣言を設計するときに足す
Manner = Openly | Stealthily
# Stealthily: 拾う・置く・渡すと、allows_stealth の操作だけ。見ていた人ごとに StealthRule の確率で気づく
# (気づいた人にはふつうの文、気づかなかった人には何も届かない)。行っているあいだは StealthRule.duration_rate 倍、物音は 1 段小さい
```

## 行為の型

```python
ObjectInteractionAttempt(actor: PersonId, obj: ObjectDeclaration, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
CarriedItemInteractionAttempt(actor: PersonId, item: ItemInstanceId, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
PersonInteractionAttempt(actor: PersonId, target: PersonId | SomeoneInTheDark, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)

ItemUseAttempt(actor: PersonId, item: ItemInstanceId)
TendAttempt(actor: PersonId, target: PersonId)
ItemHandOverAttempt(actor: PersonId, deliveries: tuple[Delivery, ...])     # 1 件以上
GroundItemPickupAttempt(actor: PersonId, item: ItemInstanceId, manner: Manner)
ItemDropAttempt(actor: PersonId, item: ItemInstanceId, manner: Manner)
SpotSearchAttempt(actor: PersonId)
EnterSectionAttempt(actor: PersonId, section: SpotSectionDeclaration)
HoldItemAttempt(actor: PersonId, item: ItemInstanceId)        # 手がふさがっていれば、今持っている物を荷にしまう
PutAwayItemAttempt(actor: PersonId, item: ItemInstanceId)
LeaveSectionAttempt(actor: PersonId)
MonsterAttackAttempt(actor: PersonId, monster: MonsterId)

TravelAttempt(actor: PersonId, destination: SpotDeclaration)
SpeechAttempt(actor: PersonId, reach: Whisper | OrdinaryVoice | Shout, content: SpeechContent)
ListeningAttempt(actor: PersonId)
WaitAttempt(actor: PersonId, reason: WaitReason | NoReason)
GroupDecisionBallotAttempt(actor: PersonId, decision: GroupDecisionDeclaration, choice: VoteFor | Abstain)
MerchantPurchaseAttempt(actor: PersonId, merchant: MerchantId, item_spec: ItemSpecDeclaration, count: int)
MerchantSaleAttempt(actor: PersonId, merchant: MerchantId, item: ItemInstanceId, count: int)
TradeProposalAttempt(actor: PersonId, partner: PersonId, offered: TradeGoods, requested: TradeGoods)
TradeAcceptanceAttempt(actor: PersonId, proposal: TradeProposalId)
TradeDeclineAttempt(actor: PersonId, proposal: TradeProposalId)
MarketBoardReadingAttempt(actor: PersonId, board: MarketBoardId)
MarketOrderPlacementAttempt(actor: PersonId, board: MarketBoardId, order: SellOrder | BuyOrder)
MarketOrderTakingAttempt(actor: PersonId, board: MarketBoardId, side: Buying | Selling, item_spec: ItemSpecDeclaration, count: int)
MarketOrderRevisionAttempt(actor: PersonId, order: MarketOrderId, price: Gold)
MarketOrderWithdrawalAttempt(actor: PersonId, order: MarketOrderId)

Whisper(to: PersonId)
SomeoneInTheDark()      # 暗がりの見分けのつかない人。相手は世界がその場から選ぶ (1 人なら決まる)。真っ暗では人がいることも分からないので使えない
VoteFor(person: PersonId)
```

## 断られたとき

```python
@final
@dataclass(frozen=True)
class ActionRefusal:
    attempt: ActionAttempt
    reason: CommonRuleRefusal | PreconditionRefusal | WorldStateRefusal
    text: TextWithAssignedPeople

CommonRuleRefusal = ActorCannotAct | Busy | NotTogether | OutOfReach | TooTired | NotAllowedInThisStage
# Busy: 前の行為を行っているあいだ (話すことだけはできる)
# ActorCannotAct: 倒れている、結末が決まった、去った人に許されない行為 (ActorRequirement)
# OutOfReach: 区画の中からしか届かない物に、外から触ろうとした

@final
@dataclass(frozen=True)
class PreconditionRefusal:
    failure: FailureReason | HiddenFailure

@final
@dataclass(frozen=True)
class WorldStateRefusal:                    # 世界を変える途中で集約が断った (満員、相手がその品を持っていない)
    code: RefusalCode                       # 集約が投げたドメイン例外の error_code。理由の文は変換役が code ごとに持つ (「荷は空だった」)
```

## 共通の前提

```python
class ActionPrerequisiteCheck:
    def refusal(
        self,
        attempt: ActionAttempt,
        facts: WorldFacts,
        stage: WorldStageDeclaration | NoWorldStages,
        rules: WorldRules,
    ) -> ActionRefusal | None: ...
```

## できること

```python
@final
@dataclass(frozen=True)
class AvailableAction:
    attempt: ActionAttempt
    standing: Doable | NotNow

@final
@dataclass(frozen=True)
class NotNow:
    reason: TextWithAssignedPeople

@final
@dataclass(frozen=True)
class AvailableActions:
    actions: tuple[AvailableAction, ...]
```

- 実際に試したときと同じ確認 (`ActionPrerequisiteCheck.refusal` と行為ごとの前提の `failure_reason`) で作る。`HiddenFailure` になった行為は入れない。いまできない行為を消さずに理由つきで出すのは design_decisions #37 のとおり (消すと、エージェントが無い操作名を作って呼ぶ)
- 行為を始めた瞬間に効果が起き、そのあと `WorldRules.action_durations` (または `InteractionDeclaration.duration`) のあいだ `PersonVitals.is_busy` が真になる。そのあいだ、話す以外の行為は `Busy` で断る
- 一覧は前提を確かめるだけで作る。考えているあいだに世界が変わるので目安で、届いたときに必ず確かめ直す。集約が断るもの (満員など) は届いたときに断る
- 行為の対象の候補は、場面 (`VisibleSurroundings`) に出ているものに限る。「誰か」(`Unidentified`) には `SomeoneInTheDark` で行う。ターンごとに振り直す呼び方 (「人影1」) は、記憶に残った呼び方が次のターンで別のものを指すので使わない (design_decisions #3)
