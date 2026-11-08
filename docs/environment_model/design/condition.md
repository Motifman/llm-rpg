# 条件 (Condition)

```python
class Condition(Protocol):
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool: ...
    def requirements(self) -> Requirements: ...
    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None: ...
    def explains_failure(self) -> bool: ...   # 自分の failure_text を持つか。根に置いた条件の文を compose が確かめる


class WorldFacts(Protocol):
    """条件と効果が世界を読む入口。集約ごとに、問い合わせだけを持つ型を返す。ロジックは持たない。同じ巻き戻しの範囲の中の変化を映す。"""
    def now(self) -> WorldTick: ...
    def rules(self) -> WorldRules: ...
    def day_night(self) -> DayNightDeclaration | NoDayNight: ...
    def nouns(self) -> DeclaredNouns: ...                   # 名詞の宣言を引く (区画の中から届く物、今の段階の宣言など)
    def random(self) -> RandomSource: ...
    def people(self) -> tuple[PersonId, ...]: ...           # 世界の全員 (死んだ人、去った人を含む)

    def whereabouts(self) -> WhereaboutsReading: ...
    def passages(self) -> PassageStatesReading: ...
    def atmospheres(self) -> SpotAtmospheresReading: ...
    def outcomes(self) -> PersonOutcomesReading: ...
    def membership(self) -> GroupMembershipReading: ...
    def clock(self) -> WorldClockReading: ...
    def weather(self) -> WeatherReading | NoWeather: ...
    def world_stage(self) -> WorldStageReading | NoWorldStages: ...
    def flags(self) -> WorldFlagsReading: ...
    def scenario_progress(self) -> ScenarioProgressReading: ...
    def latest_actions(self) -> LatestActionsReading: ...
    def vitals(self, person: PersonId) -> PersonVitalsReading: ...
    def inventory(self, person: PersonId) -> PersonInventoryReading: ...
    def item(self, item: ItemInstanceId) -> ItemReading: ...
    def object_state(self, obj: ObjectId) -> ObjectStateReading: ...
    def ground_items(self, spot: SpotId) -> GroundItemsReading: ...
    def search_progress(self, spot: SpotId) -> SpotSearchProgressReading: ...
    def missed_notices(self, person: PersonId) -> MissedNoticesReading: ...
    def group_decision(self, decision: GroupDecisionDeclaration) -> GroupDecisionReading: ...


class RandomSource(Protocol):               # 偶然の出どころ。本番はふつうの乱数、テストは決めた値を順に返す
    def next_fraction(self) -> float: ...   # 0 以上 1 未満
```

- `...Reading` は、同じ名前の集約 ([world_state.md](world_state.md)) の問い合わせのメソッドだけを持つ Protocol。本物の集約がそのまま満たす。条件は集約を書き換えられない
- 条件は、集約に直接たずねる (`facts.whereabouts().is_in_section(...)`)。集約の規則 (`can_reach` など) を窓口や条件で作り直さない。2 つの集約を組み合わせる処理 (持ち物の中の品物の種類を数える、など) は、それを使う条件の中に書く
- 窓口のメソッドは集約ごとに 1 つ。集約の問い合わせが増えても窓口は変わらない。窓口が増えるのは集約が増えたときだけ
- 条件が `facts` を受け取るのは、条件が木で、親や評価する側が子の中身を知らずに同じ形で呼ぶため。宣言である条件に集約を持たせると、宣言と run ごとの状態が混ざる
- 人の居場所を問う条件と効果 (`IsAtSpot`、`IsInSection`、`Teleport` など) は、その人が去った人として動いていれば `DepartedPerson`、それ以外は `PersonBody` の居場所を見る
- 偶然は `facts.random()` から順に引く。同じきっかけなら同じ出目、という決まりは持たない。テストは引く順に値を並べて渡し、毎回同じ結果にする
- `holds` と `failure_reason` は、どちらも呼ぶたびに偶然を引く。真偽と理由の両方が要るときは `failure_reason` だけを呼び、`None` なら真として扱う

```python
Subject = Actor | Target | ChosenByGroup | NamedPerson | EachPerson   # 誰について。1 人に決まるものだけ
# Actor: 行為をした人 / Target: 人への操作の相手 / ChosenByGroup: 集団の決定で選ばれた人
# NamedPerson(character): 宣言で名指しした人 / EachPerson: ForEveryone などで 1 人ずつ見るときの、その人
# 主語の各型は次を持つ:
#   def person_in(self, trigger: Trigger) -> PersonId: ...    # きっかけの person_as(SubjectKind) に尋ねる。NamedPerson はきっかけを見ない
#   def requirements(self) -> Requirements: ...               # 自分の SubjectKind だけを要る
ItemSubject = ThisItem                             # どの品物について (品物を使う行為、手元の道具への操作のきっかけが答える)
# ThisItem.item_in(trigger) -> ItemInstanceId。きっかけの this_item() に尋ねる

class SubjectKind(Enum):                    # ACTOR / TARGET / CHOSEN_BY_GROUP / NAMED_PERSON / EACH_PERSON

@final
@dataclass(frozen=True)
class ConditionPath:                        # 条件の木の中の位置。根からの子の位置の並び
    @classmethod
    def root(cls) -> ConditionPath: ...
    def under(self, position: int) -> ConditionPath: ...   # この位置の前に親の番号を足す。子が返した位置を、親が自分の番号で包む

@final
@dataclass(frozen=True)
class PeopleSelection:                      # 世界の全員から、where が真の人を選ぶ
    where: Condition                        # 中では EachPerson が「その人」を指す

    def select(self, facts: WorldFacts, trigger: Trigger) -> frozenset[PersonId]: ...
    def requirements(self) -> Requirements: ...   # where の要求から EACH_PERSON を除いたもの

@final
@dataclass(frozen=True)
class Requirements:
    subjects: frozenset[SubjectKind]
    uses_chance: bool
    uses_action_arguments: frozenset[ArgumentName]
    waits_for_flags: frozenset[FlagDeclaration]
    reads_world_stage: bool                          # WorldStageIs、TicksInWorldStageAtLeast、SinceWorldStageEntered
    reads_day_phases: frozenset[DayPhaseName]        # TimeOfDayIs の段階
    reads_weather: bool                              # WeatherIs
    raises_flags: frozenset[FlagDeclaration]         # RaiseFlagEffect
    closes_group_decisions: frozenset[GroupDecisionDeclaration]   # CloseGroupDecisionEffect
    may_hide_membership: bool                        # IsMember が、行う人に知りえない所属を見うる (伏せた所属)
    # 後ろの 6 つは、きっかけに要るものではなく、compose が宣言どうしを照らし合わせる材料。木のどこかにあれば根で答える

    @classmethod
    def nothing(cls) -> Requirements: ...
    def combined_with(self, other: Requirements) -> Requirements: ...
    def without_subject(self, kind: SubjectKind) -> Requirements: ...   # ForEveryone などが、中だけで使える EACH_PERSON を外へ出さない

@final
@dataclass(frozen=True)
class FailureReason:
    failed_part: ConditionPath
    text: TextAboutPeople | NoText          # NoText なら、いちばん近い親の failure_text を使う

@final
@dataclass(frozen=True)
class HiddenFailure:                        # 行う人が知りえない所属を見て偽になった
    failed_part: ConditionPath
```

### 断られた理由の文

- 作者が書いた文は `failure_text` (`TextWithUnassignedPeople`)。評価するとき、プレースホルダーに `PersonId` を当てて `TextAboutPeople` ([perception.md](perception.md)) にする。見る人ごとの呼び方 (`PersonRef`) への置き換えは、見る人が分かる場所で行う。条件は誰が見るかを知らない
- 葉とつなぎが自分の `failure_text` を持たなければ `NoText` を返し、親が自分の文で埋める。いちばん内側の文が勝つ
- 前提など、条件を置いた場所の根には `failure_text` を必ず書く。無ければ compose が `DesignFlaw` にする。ドメインは条件の種類ごとの決まった文を持たない

### 伏せた所属

一覧と理由は、行う人が知りうることだけで決める。行う人が知りうる所属は、`EVERYONE` の分け方の所属、自分の `SELF_ONLY` の所属、`members_know_each_other` の集団の仲間の所属。これ以外の所属を見て偽になった条件は `HiddenFailure` を返す。行う人はきっかけの `acting_person()` ([action.md](action.md)) に尋ね、行う人のいないきっかけ (出来事、反応など) では伏せない。

- いまできることの一覧 ([action.md](action.md) の `AvailableActions`) では、`HiddenFailure` の行為を「できる」と出す。一覧に出る / 出ないの差から所属が漏れないため
- 試したときに `HiddenFailure` なら、理由を言わずに断る。文は断りの文の表 ([world_design.md](world_design.md) の `RefusalTexts`) の、伏せた理由の文
- 試して分かることは、ゲームの手として許す。compose は、行う人に知りえない所属を見る前提を `DesignWarning` で作者に知らせる
- `IsMember` は、分け方が `EVERYONE` のとき、または `SELF_ONLY` で主語が `Actor` のときだけ、伏せられない (`may_hide_membership` が偽)。仲間どうしが知る集団でも、仲間でない人には伏せられうる

## つなぎ

```python
@final
@dataclass(frozen=True)
class AllOfCondition:
    children: tuple[Condition, ...]
    failure_text: TextWithUnassignedPeople | NoText

@final
@dataclass(frozen=True)
class AnyOfCondition:
    children: tuple[Condition, ...]
    failure_text: TextWithUnassignedPeople | NoText

@final
@dataclass(frozen=True)
class NotCondition:
    child: Condition
    failure_text: TextWithUnassignedPeople | NoText

@final
@dataclass(frozen=True)
class ForSomeoneCondition:
    people: PeopleSelection
    condition: Condition                    # 中では EachPerson が「その人」を指す
    failure_text: TextWithUnassignedPeople | NoText

@final
@dataclass(frozen=True)
class ForEveryoneCondition:
    people: PeopleSelection
    condition: Condition
    failure_text: TextWithUnassignedPeople | NoText
```

## 葉

どの葉も、下の欄のあとに `failure_text: TextWithUnassignedPeople | NoText` を持つ。葉ごとに理由を書き分けたいときだけ書く。

```python
FlagIsRaisedCondition(flag: FlagDeclaration)
FlagsRaisedAtLeastCondition(flags: tuple[FlagDeclaration, ...], count: Count)
TickAtLeastCondition(tick: WorldTick)
TickModuloCondition(divisor: Ticks, remainder: Ticks)
WorldStageIsCondition(stage: WorldStageDeclaration)
TicksInWorldStageAtLeastCondition(ticks: Ticks)
TimeOfDayIsCondition(phase: DayPhaseName)
WeatherIsCondition(weather: WeatherType)
ChanceCondition(probability: Probability)          # facts.random() から 1 つ引き、probability より小さければ真
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
SearchCountAtLeastCondition(who: Subject, count: Count)   # その人が今いる場所の回数。移動の途中なら偽
ItemAgeAtLeastCondition(item: ItemSubject, ticks: Ticks)
ItemValueIsCondition(item: ItemSubject, key: ItemStateKeyDeclaration, value: StateValue)
TicksSinceLastActionAtLeastCondition(who: Subject | Anyone, action: ActionKind | InteractionId, ticks: Ticks, since: SinceStart | SinceWorldStageEntered)
    # 起点は 最後に行った tick と since の基準 の遅いほう。まだ行っていなければ基準から数える
    # SinceStart の基準は WorldTick(0)、SinceWorldStageEntered は今の段階に入った tick (段階の無い世界では NotDeclaredInThisWorldException)
ArgumentEqualsCondition(argument: ArgumentName, expected: str)   # 操作の宣言の arguments にある文の引数だけ
HappeningHasFiredCondition(happening: HappeningDeclaration)
TicksSinceHappeningAtLeastCondition(happening: HappeningDeclaration, ticks: Ticks)   # 最後に起きた tick から数える。一度も起きていなければ偽
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

`ForEveryone` などの中では、外のきっかけを `EachPersonOf(outer, person)` ([action.md](action.md)) で包んで子に渡し、`EachPerson` はその人を指す。きっかけが答えない主語は `SubjectNotInTriggerException` になる。

`WorldStageIs`・`TicksInWorldStageAtLeast`・`TimeOfDayIs`・`WeatherIs` を、それを宣言していない世界で書くと、compose が `DesignFlaw` にする。動いているときの値は決めない。

`NamedPerson` はどこでも使える。行為の引数を見るもの (`ArgumentEqualsCondition`、`ItemByArgument`) は行為の中でしか使えず、読む引数の名前は操作の宣言の `arguments` ([world_design.md](world_design.md)) に無ければならない。compose が `requirements()` と照らし合わせ、使えない主語は `DesignFlaw` にする。
