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
    effect: Effect                          # 中では EachPerson が「その人」を指す

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
AddToObjectCountEffect(key: ObjectStateKeyDeclaration, amount: Count)
TakeFromObjectStockEffect(key: ObjectStateKeyDeclaration, amount: Count)
WriteTextEffect(key: ObjectStateKeyDeclaration, body_argument: ArgumentName)
SetItemValueEffect(item: ItemSubject, key: ItemStateKeyDeclaration, value: StateValue)
RevealObjectEffect(obj: ObjectDeclaration)
ChangePassageStateEffect(passage: PassageDeclaration, state: PassageStateName)
RevealPassageEffect(passage: PassageDeclaration)      # 道が現れる。扉を開けるのは ChangePassageStateEffect
RemovePassageEffect(passage: PassageDeclaration)      # 道が無くなる
ChangeAtmosphereEffect(spot: SpotDeclaration, lighting: Lighting | Unchanged, temperature: Temperature | Unchanged, ambient_sound: str | NoAmbientSound | Unchanged, smell: str | NoSmell | Unchanged)
GiveItemEffect(who: Subject, item_spec: ItemSpecDeclaration, count: Count)
GiveFromLootTableEffect(who: Subject, table: LootTableDeclaration)
TakeItemEffect(who: Subject, item_spec: ItemSpecDeclaration, count: Count)
MoveItemEffect(from_who: Subject, to_who: Subject, item: ItemByArgument | RandomItemOf)   # 同じ品物のまま、to_who の荷に移す。無ければ集約が断る
DepositItemToObjectEffect(who: Subject, item_spec: ItemSpecDeclaration, key: ObjectStateKeyDeclaration)
DepositGoldToObjectEffect(who: Subject, amount: Gold, key: ObjectStateKeyDeclaration)
DamageEffect(who: Subject, amount: Damage)
HealEffect(who: Subject, amount: HealAmount)
ReviveEffect(who: Subject, hp_rate: Rate)
StatusEffectInflictionEffect(who: Subject, kind: StatusEffectType, value: float, ticks: Ticks)
SatisfyNeedEffect(who: Subject, need: NeedType, amount: NeedAmount)
TeleportEffect(who: Subject, to: SpotDeclaration)
PutIntoSectionEffect(who: Subject, section: SpotSectionDeclaration)   # 本人の意思でなく区画に入れる
TakeOutOfSectionEffect(who: Subject)
RemoveBodyEffect(who: Subject)
JoinGroupEffect(who: Subject, group: GroupDeclaration)
LeaveGroupEffect(who: Subject, group: GroupDeclaration)
SetOutcomeEffect(who: Subject, outcome: OutcomeDeclaration)
EnterWorldStageEffect(stage: WorldStageDeclaration)
StartGroupDecisionEffect(decision: GroupDecisionDeclaration)
CloseGroupDecisionEffect(decision: GroupDecisionDeclaration)
```

```python
@final
@dataclass(frozen=True)
class ItemByArgument:                       # エージェントが引数で、見えている呼び方で指す品物
    argument: ArgumentName
    owner: Subject                          # 誰の持ち物から選ぶか
    place: InHands | InPack | Anywhere      # 起きている相手の手から奪うなら InHands、倒れた相手なら Anywhere

@final
@dataclass(frozen=True)
class RandomItemOf:                         # 見えない荷の中から世界が選ぶ (起きている相手の荷から抜き取る)
    owner: Subject
```

盗みは作者が書く操作。起きている相手の荷からは `RandomItemOf`、手の物は見えているので `ItemByArgument(..., InHands)`、倒れた人と死んだ人は全部見えるので `ItemByArgument(..., Anywhere)`。荷が空なら集約が断り、盗もうとした人に「荷は空だった」が届く。
