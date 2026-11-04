# 行為 (ActionAttempt)

```python
class ActionAttempt(Protocol):
    @property
    def actor(self) -> PersonId: ...
    def kind(self) -> ActionKind: ...
    def actor_requirement(self) -> ActorRequirement: ...
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]: ...
    def exertion(self) -> Exertion: ...


Trigger = ActionAttempt | HappeningFired | ReactionFired | GroupDecisionResult | WorldTimePassing

@final
@dataclass(frozen=True)
class HappeningFired:
    happening: HappeningId

@final
@dataclass(frozen=True)
class ReactionFired:
    reaction: ReactionId

@final
@dataclass(frozen=True)
class GroupDecisionResult:
    decision: GroupDecisionDeclaration
    chosen: PersonId

@final
@dataclass(frozen=True)
class WorldTimePassing:
    tick: WorldTick

ActorRequirement = LivingOnly | LivingOrDeparted
CopresenceRequirement = WithPerson | WithObject | WithGroundItem | WithMonster | WithMerchant | WithMarketBoard
Exertion = UsesBody | DoesNotUseBody
Manner = Openly | Stealthily
```

## 行為の型

```python
ObjectInteractionAttempt(actor: PersonId, obj: ObjectDeclaration, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
CarriedItemInteractionAttempt(actor: PersonId, item: ItemInstanceId, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
PersonInteractionAttempt(actor: PersonId, target: PersonId | SomeoneInTheDark, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
JointActionPreparationAttempt(actor: PersonId, obj: ObjectDeclaration, interaction: InteractionDeclaration)

ItemUseAttempt(actor: PersonId, item: ItemInstanceId)
TendAttempt(actor: PersonId, target: PersonId)
ItemHandOverAttempt(actor: PersonId, deliveries: tuple[Delivery, ...])     # 1 件以上
GroundItemPickupAttempt(actor: PersonId, item: ItemInstanceId, manner: Manner)
ItemDropAttempt(actor: PersonId, item: ItemInstanceId, manner: Manner)
SpotSearchAttempt(actor: PersonId)
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
SomeoneInTheDark()      # 暗がりの見分けのつかない人。相手は世界がその場から選ぶ (1 人なら決まる)
VoteFor(person: PersonId)
```

## 断られたとき

```python
@final
@dataclass(frozen=True)
class ActionRefusal:
    attempt: ActionAttempt
    reason: CommonRuleRefusal | PreconditionRefusal | WorldRuleRefusal
    text: TextWithPeople

CommonRuleRefusal = ActorCannotAct | NotTogether | TooTired | NotAllowedInThisStage

@final
@dataclass(frozen=True)
class PreconditionRefusal:
    failure: FailureReason | HiddenFailure

@final
@dataclass(frozen=True)
class WorldRuleRefusal:
    rule: WorldRuleViolation
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
    reason: TextWithPeople

@final
@dataclass(frozen=True)
class AvailableActions:
    actions: tuple[AvailableAction, ...]
```

- 実際に試したときと同じ確認 (`ActionPrerequisiteCheck.refusal` と行為ごとの前提の `failure_reason`) で作る。`HiddenFailure` になった行為は入れない。いまできない行為を消さずに理由つきで出すのは design_decisions #37 のとおり (消すと、エージェントが無い操作名を作って呼ぶ)
- 行為の対象の候補は、場面 (`VisibleSurroundings`) に出ているものに限る。「誰か」(`Unidentified`) には `SomeoneInTheDark` で行う。ターンごとに振り直す呼び方 (「人影1」) は、記憶に残った呼び方が次のターンで別のものを指すので使わない (design_decisions #3)
