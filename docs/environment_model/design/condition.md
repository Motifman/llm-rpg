# 条件 (Condition)

```python
class Condition(Protocol):
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool: ...
    def requirements(self) -> Requirements: ...
    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | None: ...


class WorldFacts(Protocol):
    """条件が世界を読む口。読むだけで、同じ巻き戻しの範囲の中の変化を映す。"""
    def now(self) -> WorldTick: ...
    def flag_is_raised(self, flag: FlagDeclaration) -> bool: ...
    def world_stage(self) -> WorldStageId | NoWorldStages: ...
    def ticks_in_world_stage(self) -> int: ...
    def time_of_day(self) -> TimeOfDay | NoDayNight: ...
    def weather(self) -> WeatherState | NoWeather: ...
    def happening_last_fired_at(self, happening: HappeningDeclaration) -> WorldTick | NeverFired: ...
    def object_value(self, key: ObjectStateKeyDeclaration) -> StateValue: ...
    def item_count(self, person: PersonId, item_spec: ItemSpecDeclaration) -> int: ...
    def spot_of(self, occupant: Occupant) -> SpotId | TravelInProgress: ...
    def is_member(self, person: PersonId, group: GroupDeclaration) -> bool: ...
    def gold_of(self, person: PersonId) -> int: ...
    def need_of(self, person: PersonId, need: NeedType) -> int: ...
    def life_state(self, person: PersonId) -> LifeState: ...
    def outcome_of(self, person: PersonId) -> Outcome: ...
    def search_count(self, person: PersonId, spot: SpotId) -> int: ...
    def ticks_since_last_action(self, who: PersonId | Anyone, action: ActionKind | InteractionId, since: SinceStart | SinceWorldStageEntered) -> int | NeverDone: ...
    def people(self, scope: PeopleScope) -> tuple[PersonId, ...]: ...
    def roll(self, occasion: ChanceOccasion) -> float: ...


@final
@dataclass(frozen=True)
class ChanceOccasion:
    trigger: Trigger
    tick: WorldTick
    position: ConditionPath | EffectPath


Subject = Actor | Target | Chosen | Named | Bound   # 誰について。1 人に決まるものだけ
ItemSubject = ThisItem                             # どの品物について (品物を使う行為、手元の道具への操作のきっかけが答える)

@final
@dataclass(frozen=True)
class PeopleSelection:
    among: PeopleScope
    where: Condition

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
    text: str
```

## つなぎ

```python
@final
@dataclass(frozen=True)
class AllOfCondition:
    children: tuple[Condition, ...]
    failure_text: str | NoText

@final
@dataclass(frozen=True)
class AnyOfCondition:
    children: tuple[Condition, ...]
    failure_text: str | NoText

@final
@dataclass(frozen=True)
class NotCondition:
    child: Condition
    failure_text: str | NoText

@final
@dataclass(frozen=True)
class ForSomeoneCondition:
    people: PeopleSelection
    condition: Condition                    # 中では Bound が「その人」を指す
    failure_text: str | NoText

@final
@dataclass(frozen=True)
class ForEveryoneCondition:
    people: PeopleSelection
    condition: Condition
    failure_text: str | NoText
```

## 葉

```python
FlagIsRaisedCondition(flag: FlagDeclaration)
FlagsRaisedAtLeastCondition(flags: tuple[FlagDeclaration, ...], count: int)
TickAtLeastCondition(tick: int)
TickModuloCondition(divisor: int, remainder: int)
WorldStageIsCondition(stage: WorldStageDeclaration)
TicksInWorldStageAtLeastCondition(ticks: int)
TimeOfDayIsCondition(phase: DayPhaseName)
WeatherIsCondition(weather: WeatherType)
ChanceCondition(probability: Probability)
ObjectValueIsCondition(key: ObjectStateKeyDeclaration, value: StateValue)
ObjectCountAtLeastCondition(key: ObjectStateKeyDeclaration, count: int)
ObjectCountGreaterThanCondition(key: ObjectStateKeyDeclaration, other: ObjectStateKeyDeclaration)
ObjectStockAtLeastCondition(key: ObjectStateKeyDeclaration, amount: int)
HasItemCondition(who: Subject, item_spec: ItemSpecDeclaration, count: int)
IsAtSpotCondition(who: Subject, spot: SpotDeclaration)
PeopleCountAtLeastCondition(people: PeopleSelection, count: int)
IsMemberCondition(who: Subject, group: GroupDeclaration)
IsDownCondition(who: Subject)
IsAliveCondition(who: Subject)
OutcomeIsCondition(who: Subject, outcome: Outcome)
GoldAtLeastCondition(who: Subject, amount: int)
NeedAtLeastCondition(who: Subject, need: NeedType, value: int)
SearchCountAtLeastCondition(who: Subject, count: int)
ItemAgeAtLeastCondition(item: ItemSubject, ticks: int)
ItemValueIsCondition(item: ItemSubject, key: ItemStateKeyDeclaration, value: StateValue)
TicksSinceLastActionAtLeastCondition(who: Subject | Anyone, action: ActionKind | InteractionId, ticks: int, since: SinceStart | SinceWorldStageEntered)
ArgumentEqualsCondition(argument: ArgumentName, expected: str)
HappeningHasFiredCondition(happening: HappeningDeclaration)
TicksSinceHappeningAtLeastCondition(happening: HappeningDeclaration, ticks: int)
```
