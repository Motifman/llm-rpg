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
PersonInteractionAttempt(actor: PersonId, target: PersonId, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
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
VoteFor(person: PersonId)
```

## 断られたとき

```python
@final
@dataclass(frozen=True)
class ActionRefusal:
    attempt: ActionAttempt
    reason: CommonRuleRefusal | PreconditionRefusal | WorldRuleRefusal
    text: str

CommonRuleRefusal = ActorCannotAct | NotTogether | TooTired | NotAllowedInThisStage

@final
@dataclass(frozen=True)
class PreconditionRefusal:
    failure: FailureReason

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
