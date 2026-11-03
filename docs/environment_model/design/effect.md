# 効果 (Effect)

```python
class Effect(Protocol):
    # 断るときは、集約がドメイン例外を投げる
    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None: ...
    def requirements(self) -> Requirements: ...


class WorldAggregates(Protocol):
    """効果が書き換える集約を取り出す口。"""
    def flags(self) -> WorldFlags: ...
    def passages(self) -> PassageStates: ...
    def atmospheres(self) -> SpotAtmospheres: ...
    def whereabouts(self) -> Whereabouts: ...
    def vitals(self, person: PersonId) -> PersonVitals: ...
    def outcomes(self) -> PersonOutcomes: ...
    def membership(self) -> GroupMembership: ...
    def inventory(self, person: PersonId) -> PersonInventory: ...
    def item(self, item: ItemInstanceId) -> Item: ...
    def object_state(self, obj: ObjectId) -> ObjectState: ...
    def ground_items(self, spot: SpotId) -> GroundItems: ...
    def world_stage(self) -> WorldStage: ...
    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecision: ...
    def weather(self) -> Weather: ...
    def monster(self, monster: MonsterId) -> Monster: ...
```

## つなぎ

```python
@final
@dataclass(frozen=True)
class SequenceEffect:
    steps: tuple[Effect, ...]

@final
@dataclass(frozen=True)
class ConditionalEffect:
    condition: Condition
    then: Effect
    otherwise: Effect | NoEffect

@final
@dataclass(frozen=True)
class RandomBranchEffect:
    branches: tuple[tuple[Weight, Effect], ...]

@final
@dataclass(frozen=True)
class ForEveryoneEffect:
    people: PeopleSelection
    effect: Effect                          # 中では Bound が「その人」を指す

@final
@dataclass(frozen=True)
class ForSomeoneEffect:
    people: PeopleSelection
    effect: Effect
```

## 葉

```python
RaiseFlagEffect(flag: FlagDeclaration)
LowerFlagEffect(flag: FlagDeclaration)
SetObjectValueEffect(key: ObjectStateKeyDeclaration, value: StateValue)
AddToObjectCountEffect(key: ObjectStateKeyDeclaration, amount: int)
TakeFromObjectStockEffect(key: ObjectStateKeyDeclaration, amount: int)
WriteTextEffect(key: ObjectStateKeyDeclaration, body_argument: ArgumentName)
RevealObjectEffect(obj: ObjectDeclaration)
ChangePassageStateEffect(passage: PassageDeclaration, state: PassageStateName)
OpenPassageEffect(passage: PassageDeclaration)
ClosePassageOffEffect(passage: PassageDeclaration)
ChangeAtmosphereEffect(spot: SpotDeclaration, change: AtmosphereChange)
GiveItemEffect(who: Subject, item_spec: ItemSpecDeclaration, count: int)
GiveFromLootTableEffect(who: Subject, table: LootTableDeclaration)
TakeItemEffect(who: Subject, item_spec: ItemSpecDeclaration, count: int)
DepositItemToObjectEffect(who: Subject, item_spec: ItemSpecDeclaration, key: ObjectStateKeyDeclaration)
DepositGoldToObjectEffect(who: Subject, amount: int, key: ObjectStateKeyDeclaration)
DamageEffect(who: Subject, amount: int)
HealEffect(who: Subject, amount: int)
ReviveEffect(who: Subject, hp_rate: float)
StatusEffectInflictionEffect(who: Subject, kind: StatusEffectType, value: float, ticks: int)
SatisfyNeedEffect(who: Subject, need: NeedType, amount: int)
TeleportEffect(who: Subject, to: SpotDeclaration)
RemoveBodyEffect(who: Subject)
JoinGroupEffect(who: Subject, group: GroupDeclaration)
LeaveGroupEffect(who: Subject, group: GroupDeclaration)
SetOutcomeEffect(who: Subject, outcome: Outcome)
EnterWorldStageEffect(stage: WorldStageDeclaration)
StartGroupDecisionEffect(decision: GroupDecisionDeclaration)
CloseGroupDecisionEffect(decision: GroupDecisionDeclaration)
```
