# 条件 (Condition)

```python
class Condition(Protocol):
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool: ...
    def requirements(self) -> Requirements: ...
    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None: ...


class WorldFacts(Protocol):
    """条件が世界を読む口。読むだけで、同じ巻き戻しの範囲の中の変化を映す。"""
    def now(self) -> WorldTick: ...
    def flag_is_raised(self, flag: FlagDeclaration) -> bool: ...
    def world_stage(self) -> WorldStageDeclaration | NoWorldStages: ...   # WorldStage を宣言しない世界は NoWorldStages
    def ticks_in_world_stage(self) -> Ticks: ...
    def time_of_day(self) -> TimeOfDay | NoDayNight: ...
    def weather(self) -> WeatherState | NoWeather: ...
    def happening_last_fired_at(self, happening: HappeningDeclaration) -> WorldTick | NeverFired: ...
    def object_value(self, key: ObjectStateKeyDeclaration) -> StateValue: ...
    def item_count(self, person: PersonId, item_spec: ItemSpecDeclaration) -> Count: ...
    def is_holding(self, person: PersonId, item_spec: ItemSpecDeclaration) -> bool: ...
    def spot_of(self, occupant: Occupant) -> SpotId | TravelInProgress: ...
    def is_member(self, person: PersonId, group: GroupDeclaration) -> bool: ...
    def gold_of(self, person: PersonId) -> Gold: ...
    def hunger_of(self, person: PersonId) -> HungerAmount: ...
    def fatigue_of(self, person: PersonId) -> FatigueAmount: ...
    def life_state(self, person: PersonId) -> LifeState: ...
    def outcome_of(self, person: PersonId) -> Outcome | Undecided: ...
    def all_outcomes_decided(self) -> bool: ...
    def search_count(self, person: PersonId, spot: SpotId) -> Count: ...
    def ticks_since_last_action(self, who: PersonId | Anyone, action: ActionKind | InteractionId, since: SinceStart | SinceWorldStageEntered) -> int | NeverDone: ...
    def people(self) -> tuple[PersonId, ...]: ...           # 世界の全員 (死んだ人、去った人を含む)
    def roll(self, occasion: ChanceOccasion) -> float: ...


@final
@dataclass(frozen=True)
class ChanceOccasion:
    trigger: Trigger
    tick: WorldTick
    position: ConditionPath | EffectPath


Subject = Actor | Target | ChosenByGroup | NamedPerson | EachPerson   # 誰について。1 人に決まるものだけ
# Actor: 行為をした人 / Target: 人への操作の相手 / ChosenByGroup: 集団の決定で選ばれた人
# NamedPerson(character): 宣言で名指しした人 / EachPerson: ForEveryone などで 1 人ずつ見るときの、その人
ItemSubject = ThisItem                             # どの品物について (品物を使う行為、手元の道具への操作のきっかけが答える)

@final
@dataclass(frozen=True)
class PeopleSelection:                      # 世界の全員から、where が真の人を選ぶ
    where: Condition                        # 中では EachPerson が「その人」を指す

    def select(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]: ...
    def requirements(self) -> Requirements: ...

@final
@dataclass(frozen=True)
class Requirements:
    subjects: frozenset[SubjectKind]
    uses_chance: bool
    uses_action_arguments: bool
    waits_for_flags: frozenset[FlagDeclaration]

@final
@dataclass(frozen=True)
class FailureReason:
    failed_part: ConditionPath
    text: TextWithPeople                    # 作者の failure_text の穴を評価のときの人で埋めた文。無ければ条件の種類ごとの決まった文

@final
@dataclass(frozen=True)
class HiddenFailure:                        # 誰が何者かで決まる条件 (伏せた属性を見る条件)。理由を見せると伏せた役割が分かる
    failed_part: ConditionPath
```

満たしていない条件のうち、`FailureReason` は「いまできない」に理由つきで出し、`HiddenFailure` は行為ごと一覧に出さない ([action.md](action.md) の `AvailableActions`)。

## つなぎ

```python
@final
@dataclass(frozen=True)
class AllOfCondition:
    children: tuple[Condition, ...]
    failure_text: TextWithPersonHoles | NoText

@final
@dataclass(frozen=True)
class AnyOfCondition:
    children: tuple[Condition, ...]
    failure_text: TextWithPersonHoles | NoText

@final
@dataclass(frozen=True)
class NotCondition:
    child: Condition
    failure_text: TextWithPersonHoles | NoText

@final
@dataclass(frozen=True)
class ForSomeoneCondition:
    people: PeopleSelection
    condition: Condition                    # 中では EachPerson が「その人」を指す
    failure_text: TextWithPersonHoles | NoText

@final
@dataclass(frozen=True)
class ForEveryoneCondition:
    people: PeopleSelection
    condition: Condition
    failure_text: TextWithPersonHoles | NoText
```

## 葉

```python
FlagIsRaisedCondition(flag: FlagDeclaration)
FlagsRaisedAtLeastCondition(flags: tuple[FlagDeclaration, ...], count: Count)
TickAtLeastCondition(tick: WorldTick)
TickModuloCondition(divisor: Ticks, remainder: Ticks)
WorldStageIsCondition(stage: WorldStageDeclaration)
TicksInWorldStageAtLeastCondition(ticks: Ticks)
TimeOfDayIsCondition(phase: DayPhaseName)
WeatherIsCondition(weather: WeatherType)
ChanceCondition(probability: Probability)
ObjectValueIsCondition(key: ObjectStateKeyDeclaration, value: StateValue)
ObjectCountAtLeastCondition(key: ObjectStateKeyDeclaration, count: Count)
ObjectCountGreaterThanCondition(key: ObjectStateKeyDeclaration, other: ObjectStateKeyDeclaration)
ObjectStockAtLeastCondition(key: ObjectStateKeyDeclaration, amount: Count)
HasItemCondition(who: Subject, item_spec: ItemSpecDeclaration, count: Count)
IsAtSpotCondition(who: Subject, spot: SpotDeclaration)
IsInSectionCondition(who: Subject, section: SpotSectionDeclaration)
IsHoldingCondition(who: Subject, item_spec: ItemSpecDeclaration)   # 手に持っている。作者が「手に持っていれば」を書くとき
AllOutcomesDecidedCondition()
PeopleCountAtLeastCondition(people: PeopleSelection, count: Count)
IsMemberCondition(who: Subject, group: GroupDeclaration)
IsDownCondition(who: Subject)
IsAliveCondition(who: Subject)
OutcomeIsCondition(who: Subject, outcome: Outcome)          # Died | DeclaredOutcome
GoldAtLeastCondition(who: Subject, amount: Gold)
HungerAtLeastCondition(who: Subject, value: HungerAmount)
FatigueAtLeastCondition(who: Subject, value: FatigueAmount)
SearchCountAtLeastCondition(who: Subject, count: Count)
ItemAgeAtLeastCondition(item: ItemSubject, ticks: Ticks)
ItemValueIsCondition(item: ItemSubject, key: ItemStateKeyDeclaration, value: StateValue)
TicksSinceLastActionAtLeastCondition(who: Subject | Anyone, action: ActionKind | InteractionId, ticks: Ticks, since: SinceStart | SinceWorldStageEntered)
ArgumentEqualsCondition(argument: ArgumentName, expected: str)
HappeningHasFiredCondition(happening: HappeningDeclaration)
TicksSinceHappeningAtLeastCondition(happening: HappeningDeclaration, ticks: Ticks)
```

## 置いた場所ごとに使える主語

| 置いた場所 | 使える主語 |
|---|---|
| 物体や持ち物への操作、区画の入る条件 | `Actor` |
| 人への操作 | `Actor`、`Target` |
| 見つかる物 | `Actor` (見つけた人) |
| 集団の決定の結果 (`when_decided`) | `ChosenByGroup` |
| 出来事、反応、二人で合わせる操作の結果 | なし |
| `ForEveryone` / `ForSomeone` / `PeopleSelection` の中 | 外の主語 + `EachPerson` |

`NamedPerson` はどこでも使える。行為の引数を見るもの (`ArgumentEqualsCondition`、`ItemByArgument`) は行為の中でしか使えない。compose が `requirements()` と照らし合わせ、使えない主語は `DesignFlaw` にする。
