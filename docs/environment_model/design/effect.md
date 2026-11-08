# 効果 (Effect)

```python
class Effect(Protocol):
    # 断るときは、集約がドメイン例外を投げる。効果は自分で断らない
    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None: ...
    def requirements(self) -> Requirements: ...


class WorldAggregates(Protocol):
    """効果が書き換える集約を取り出す入口。読むときは facts (condition.md の WorldFacts) を使う。"""
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
    def search_progress(self, spot: SpotId) -> SpotSearchProgress: ...
    def missed_notices(self, person: PersonId) -> MissedNotices: ...
    def world_stage(self) -> WorldStage: ...
    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecision: ...
    def weather(self) -> Weather: ...

    def bring_item_into_world(self, spec: ItemSpecDeclaration, now: WorldTick) -> ItemInstanceId: ...
        # 新しい ID (uuid) を決め、Item.come_into_world で作って登録し、ID を返す。登場人物の initial_items もここを通る
    def take_item_out_of_world(self, item: ItemInstanceId) -> None: ...
        # Item.leave_world を呼び、登録から外す
```

- `bring_item_into_world` は集約の操作ではなく「作って入れる」リポジトリの操作なので、値を返す
- 品物の ID (`ItemInstanceId`) はエージェントに見せない。エージェントには場面の呼び方で見せ、trace には ID と並べて品物の名前を出す
- モンスターの集約は #1971 で足す

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
class RandomBranchEffect:                  # facts.random() から 1 つ引き、重みの割合で枝を選ぶ
    branches: tuple[tuple[Weight, Effect], ...]   # Weight は 1 以上の整数

@final
@dataclass(frozen=True)
class ForEveryoneEffect:
    people: PeopleSelection
    effect: Effect                          # 中では EachPerson が「その人」を指す

@final
@dataclass(frozen=True)
class ForSomeoneEffect:                    # 選ばれた人から facts.random() で 1 人を選んで当てる。誰もいなければ何も起きない
    people: PeopleSelection
    effect: Effect
```

## 葉

```python
RaiseFlagEffect(flag: FlagDeclaration)
LowerFlagEffect(flag: FlagDeclaration)
SetObjectValueEffect(key: ObjectStateKeyDeclaration, value: StateValue)
AddToObjectCountEffect(key: ObjectStateKeyDeclaration, amount: Count)
SubtractFromObjectCountEffect(key: ObjectStateKeyDeclaration, amount: Count)   # ObjectState.subtract_from_count。0 を下回るなら集約が断る
TakeFromObjectStockEffect(key: ObjectStateKeyDeclaration, amount: Count)
WriteTextEffect(key: ObjectStateKeyDeclaration, body_argument: ArgumentName)
SetItemValueEffect(item: ItemSubject, key: ItemStateKeyDeclaration, value: StateValue)
RevealObjectEffect(obj: ObjectDeclaration)
ChangePassageStateEffect(passage: PassageDeclaration, state: PassageStateName)
RevealPassageEffect(passage: PassageDeclaration)      # 道が現れる。扉を開けるのは ChangePassageStateEffect
RemovePassageEffect(passage: PassageDeclaration)      # 道が無くなる
ChangeAtmosphereEffect(spot: SpotDeclaration, lighting: Lighting | Unchanged, temperature: Temperature | Unchanged, ambient_sound: DescriptionText | NoAmbientSound | Unchanged, smell: DescriptionText | NoSmell | Unchanged)
GiveItemEffect(who: Subject, item_spec: ItemSpecDeclaration, count: Count)   # bring_item_into_world で count 個作り、who の荷に入れる
TakeItemEffect(who: Subject, item_spec: ItemSpecDeclaration, count: Count)   # 荷から先に、足りなければ手からも取り、世界から消す。持っている数が足りなければ PersonInventory が断る (1 つも取らない)
MoveItemEffect(from_who: Subject, to_who: Subject, item: ItemByArgument | RandomItemOf)   # from_who の持ち物から item で選び、同じ品物のまま to_who の荷に移す。無ければ集約が断る
DepositItemToObjectEffect(who: Subject, item_spec: ItemSpecDeclaration, key: ObjectStateKeyDeclaration)   # who から 1 つ手放して世界から消し、物の数の鍵を 1 足す
DepositGoldToObjectEffect(who: Subject, amount: Gold, key: ObjectStateKeyDeclaration)   # who が amount を払い、物の数の鍵を amount 足す
DamageEffect(who: Subject, amount: Damage)   # 倒れた理由は trigger.fall_cause_for(相手) に尋ねる
HealEffect(who: Subject, amount: HealAmount)
ReviveEffect(who: Subject, hp_rate: Rate)
SatisfyHungerEffect(who: Subject, amount: HungerAmount)   # 規則は facts.rules().hunger
RestEffect(who: Subject, amount: FatigueAmount)   # 規則は facts.rules().fatigue
TeleportEffect(who: Subject, to: SpotDeclaration)
PutIntoSectionEffect(who: Subject, section: SpotSectionDeclaration)   # 本人の意思でなく区画に入れる。定員に数えない人 (倒れた人、死んだ人) は facts.vitals で生死を読んで集める
TakeOutOfSectionEffect(who: Subject)
RemoveBodyEffect(who: Subject)
JoinGroupEffect(who: Subject, group: GroupDeclaration)
LeaveGroupEffect(who: Subject, group: GroupDeclaration)
SetOutcomeEffect(who: Subject, outcome: OutcomeDeclaration)
EnterWorldStageEffect(stage: WorldStageDeclaration)
StartGroupDecisionEffect(rules: GroupDecisionRulesDeclaration)   # 投票する人と候補を rules.voters / rules.choices で選んで始める
CloseGroupDecisionEffect(decision: GroupDecisionDeclaration)
```

```python
@final
@dataclass(frozen=True)
class ItemByArgument:                       # エージェントが指した品物。行為の引数 (ActionArguments) の ItemInstanceId を読む。呼び方から ID を引くのは外側
    argument: ArgumentName
    place: InHands | InPack | Anywhere      # 起きている相手の手から奪うなら InHands、倒れた相手なら Anywhere
                                            # InHands は PersonInventory.give_up_held、InPack は give_up_packed、Anywhere は give_up を呼ぶ。指した場所に無ければ集約が断る

@final
@dataclass(frozen=True)
class RandomItemOf:                         # 見えない荷の中から世界が選ぶ (起きている相手の荷から抜き取る)。facts.inventory(from_who).random_packed_item(facts.random()) で荷の物を 1 つ選び、give_up_packed で手放す。荷が空なら PersonInventory が断る。手の物は選ばない
    pass
```

誰の持ち物から選ぶかは `MoveItemEffect.from_who` だけが持つ。選び方にも持たせると、手放す人を 2 か所に書けて食い違うため (D2024)。

盗みは作者が書く操作。起きている相手の荷からは `RandomItemOf`、手の物は見えているので `ItemByArgument(..., InHands)`、倒れた人と死んだ人は全部見えるので `ItemByArgument(..., Anywhere)`。荷が空なら集約が断り、盗もうとした人に「荷は空だった」が届く。

## 倒れた理由

`DamageEffect` は、傷ついた人の倒れた理由をきっかけに尋ねる (`trigger.fall_cause_for(victim)`、[action.md](action.md))。効果はきっかけの種類を見分けない。

| きっかけ | 倒れた理由 |
|---|---|
| 人の行為 | 傷ついたのが本人以外なら `StruckByPerson(行った人)`、本人なら `WorldHappening()` (罠に触れた本人が傷つくなど) |
| 出来事、反応、二人で合わせる操作、集団の決定、時間が進んだこと | `WorldHappening()` |
| `EachPersonOf` | 外のきっかけに任せる |

空腹で倒れる (`Starvation`) のは `PersonVitals.pass_time` が決めるので、ここには出てこない。

## 作らないもの

- `GiveFromLootTableEffect`: `LootTableDeclaration` を設計するときに足す
- 状態効果を付ける効果: 何をする効果かを #2014 で決めてから足す
