# 設計図 (WorldDesign)

シナリオが宣言したもの。run の間は変わらない。

```python
# 名詞の宣言

@final
@dataclass(frozen=True)
class FlagDeclaration:
    flag_id: FlagId
    meaning: str
    initially_raised: bool

@final
@dataclass(frozen=True)
class SpotDeclaration:
    spot_id: SpotId
    name: str
    description: str
    atmosphere: SpotAtmosphere

@final
@dataclass(frozen=True)
class SpotAtmosphere:
    lighting: Lighting
    outdoor: bool                           # 明るさの計算の材料 (LightingConditions.outdoor)
    temperature: Temperature
    ambient_sound: str | NoAmbientSound
    smell: str | NoSmell

    def with_changes(
        self,
        lighting: Lighting | Unchanged,
        temperature: Temperature | Unchanged,
        ambient_sound: str | NoAmbientSound | Unchanged,
        smell: str | NoSmell | Unchanged,
    ) -> "SpotAtmosphere": ...

@final
@dataclass(frozen=True)
class SpotSectionDeclaration:               # 場所の中の、体で入る一角 (籠の中、小舟、檻、見張り台)。中と外は同じ場所
    section_id: SpotSectionId
    spot_id: SpotId
    name: str
    enter_label: str                        # 「籠に乗り込む」
    leave_label: str                        # 「籠から降りる」
    enter_text: TextWithUnassignedPeople  # 入った本人の体の刺激
    leave_text: TextWithUnassignedPeople
    exertion: Exertion
    duration: Ticks | DefaultDuration
    capacity: Capacity | NoCapacity
    reachable_objects: tuple[ObjectId, ...] # 中からしか届かない物
    entry_condition: Condition              # 書かなければ、いつでも入れる
    perceived_as: PerceptionDeclaration

@final
@dataclass(frozen=True)
class PassageDeclaration:
    passage_id: PassageId
    ends: tuple[SpotId, SpotId]
    two_way: bool
    travel_ticks: Ticks
    states: tuple[PassageStateDeclaration, ...]   # 書かなければ「通れる、減衰 0」の 1 つ
    initial_state: PassageStateName
    traversal_condition: Condition

    def allows(self, state: PassageStateName) -> bool: ...
    def state(self, name: PassageStateName) -> PassageStateDeclaration: ...

@final
@dataclass(frozen=True)
class PassageStateDeclaration:
    name: PassageStateName
    display_name: str
    traversable: bool
    sound_loss: SoundLoss

@final
@dataclass(frozen=True)
class ObjectStateKeyDeclaration:
    object_id: ObjectId
    key: StateKeyId
    kind: FlagStateKind | CountStateKind | ChoiceStateKind | StockStateKind | WrittenTextStateKind
    initial: StateValue

@final
@dataclass(frozen=True)
class ObjectDeclaration:
    object_id: ObjectId
    spot_id: SpotId
    name: str
    description: str
    appearance: ObjectAppearance
    interactions: tuple[InteractionDeclaration, ...]
    state_keys: tuple[ObjectStateKeyDeclaration, ...]

@final
@dataclass(frozen=True)
class ObjectAppearance:
    seen_in_dark: bool                      # 光る物、大きな物。暗い・真っ暗でも場面に出る
    hidden_until_revealed: bool             # RevealObjectEffect までは場面に出ず、操作もできない

@final
@dataclass(frozen=True)
class ItemSpecDeclaration:
    item_spec_id: ItemSpecId
    name: str
    description: str
    on_use: Effect | NotUsable
    interactions: tuple[InteractionDeclaration, ...]
    state_keys: tuple[ItemStateKeyDeclaration, ...]
    lights_up: LitWhen | NotALightSource     # LitWhen(key, value): その状態の値のとき灯っている。手に持っているあいだ場所を照らす
    hands_needed: HandsNeeded                # 1 (カンテラ) / 2 (つるはし)。書かなければ 1

@final
@dataclass(frozen=True)
class GroupDeclaration:
    group_id: GroupId
    grouping: GroupingDeclaration
    name: str
    members_know_each_other: bool
    shared_description: str | NoSharedDescription

    def members_can_change(self) -> bool: ...

@final
@dataclass(frozen=True)
class GroupingDeclaration:
    grouping_id: GroupingId
    name: str
    visibility: MembershipVisibility        # EVERYONE / SELF_ONLY / NOBODY
    changes: bool

@final
@dataclass(frozen=True)
class CharacterDeclaration:
    person_id: PersonId
    persona: Persona
    appearance: str
    spawn_spot: SpotId
    initial_items: tuple[ItemSpecId, ...]
    initial_held: tuple[ItemSpecId, ...]     # initial_items のうち、最初から手に持っている物
    initial_groups: tuple[GroupId, ...]
    knows_at_start: tuple[PersonId, ...]

@final
@dataclass(frozen=True)
class WorldStageDeclaration:
    stage_id: WorldStageId
    name: str
    description: str
    allowed_actions: frozenset[ActionKind | InteractionId] | AllActionsAllowed
    when_entered: Effect
    when_left: Effect

@final
@dataclass(frozen=True)
class GroupDecisionDeclaration:
    decision_id: GroupDecisionId
    name: str
    voters: PeopleSelection
    choices: PeopleSelection
    abstain_allowed: bool
    reveals_ballots: bool                   # 集計のとき、誰が誰に入れたかを知らせるか
    when_decided: Effect
    when_undecided: Effect

@final
@dataclass(frozen=True)
class OutcomeDeclaration:
    outcome_id: OutcomeId
    name: str                               # 「救出」
    announcement: TextWithUnassignedPeople # 「{person}は昇降機で外へ出た。」

@final
@dataclass(frozen=True)
class DiscoverableDeclaration:
    discoverable_id: DiscoverableId
    spot_id: SpotId
    found_text: TextWithUnassignedPeople   # 見つけた本人の体の刺激になる
    condition: Condition
    when_found: Effect
    finding: Finding                         # ONCE_IN_WORLD: 誰かが見つけたら終わり / ONCE_PER_PERSON: 人ごとに 1 回


class DeclaredNouns:
    """名詞の宣言を集め、名前から宣言を引く。"""

    def __init__(
        self,
        flags: Iterable[FlagDeclaration],
        spots: Iterable[SpotDeclaration],
        passages: Iterable[PassageDeclaration],
        objects: Iterable[ObjectDeclaration],
        item_specs: Iterable[ItemSpecDeclaration],
        groupings: Iterable[GroupingDeclaration],
        groups: Iterable[GroupDeclaration],
        characters: Iterable[CharacterDeclaration],
        world_stages: Iterable[WorldStageDeclaration],
        group_decisions: Iterable[GroupDecisionDeclaration],
        sections: Iterable[SpotSectionDeclaration],
        outcomes: Iterable[OutcomeDeclaration],
    ) -> None: ...

    def flag(self, name: str, at: DesignLocation) -> FlagDeclaration: ...
    def spot(self, name: str, at: DesignLocation) -> SpotDeclaration: ...
    def passage(self, name: str, at: DesignLocation) -> PassageDeclaration: ...
    def object(self, name: str, at: DesignLocation) -> ObjectDeclaration: ...
    def object_state_key(self, object_name: str, key: str, at: DesignLocation) -> ObjectStateKeyDeclaration: ...
    def item_spec(self, name: str, at: DesignLocation) -> ItemSpecDeclaration: ...
    def group(self, name: str, at: DesignLocation) -> GroupDeclaration: ...
    def groups_in(self, grouping: GroupingDeclaration) -> tuple[GroupDeclaration, ...]: ...
    def character(self, name: str, at: DesignLocation) -> CharacterDeclaration: ...
    def world_stage(self, name: str, at: DesignLocation) -> WorldStageDeclaration: ...
    def group_decision(self, name: str, at: DesignLocation) -> GroupDecisionDeclaration: ...
    def section(self, name: str, at: DesignLocation) -> SpotSectionDeclaration: ...
    def sections_at(self, spot: SpotId) -> tuple[SpotSectionDeclaration, ...]: ...
    def outcome(self, name: str, at: DesignLocation) -> OutcomeDeclaration: ...
    # 引けなかった名前は UnknownNameFlaw を投げる。読む側はその宣言 1 つを諦めて DesignFlaw を記録し、次へ進む


# 動詞の宣言

@final
@dataclass(frozen=True)
class InteractionDeclaration:
    interaction_id: InteractionId
    display_label: str
    precondition: Condition
    effect: Effect
    success_text: TextWithUnassignedPeople # 行った本人の体の刺激になる
    shows_on_success: tuple[ShownToActor, ...]
    exertion: Exertion
    actor_requirement: ActorRequirement
    perceived_as: PerceptionDeclaration
    reaches_unseen: bool                    # 暗がりの誰か (SomeoneInTheDark) に向けてできるか
    duration: Ticks | DefaultDuration       # 行っているあいだ。書かなければ WorldRules.action_durations
    allows_stealth: bool                    # こっそり行える (Stealthily) か

ShownToActor = PeopleCountAt | WrittenTextOf   # 成功したとき本人だけに見せる、世界の今の値。success_text の後ろに付ける
PeopleCountAt(spot: SpotDeclaration)
WrittenTextOf(key: ObjectStateKeyDeclaration)

@final
@dataclass(frozen=True)
class HappeningDeclaration:
    happening_id: HappeningId
    condition: Condition
    effect: Effect
    once: bool
    notice: HappeningNotice | NoNotice

HappeningNotice = SightAt | SoundFrom | AnnouncementTo

@final
@dataclass(frozen=True)
class SightAt:
    spot: SpotDeclaration
    texts: SightTextsDeclaration
    salience: Salience

@final
@dataclass(frozen=True)
class SoundFrom:
    spot: SpotDeclaration
    sound: SoundDeclaration
    salience: Salience

@final
@dataclass(frozen=True)
class AnnouncementTo:
    audience: PeopleSelection
    text: TextWithUnassignedPeople
    salience: Salience

@final
@dataclass(frozen=True)
class PerceptionDeclaration:                # 行為が周りにどう知覚されるか
    witness: SightTextsDeclaration
    target: SightTextsDeclaration | NoTarget
    sound: SoundDeclaration | Silent
    seen_in_dark: bool                              # 真っ暗でも dim の文が届く (光る、大きな動き)
    announcement: AnnouncementTo | NoAnnouncement   # 緊急の招集など、居場所に関わらず知らせるとき
    on_failure: SightTextsDeclaration | NoFailureWitness       # 前提か世界を変える途中で断られたとき、見ていた人への文。書かなければ届けない (警告もしない)
    salience: Salience                              # Notable: 外側が考え直す目安になる / Background: ならない

@final
@dataclass(frozen=True)
class SoundDeclaration:
    loudness: Loudness                      # 書かなければ、開け閉めは大きい、壊すはとても大きい、ほかはふつう
    clear: TextWithUnassignedPeople       # 人のプレースホルダーは声 (話す) のときだけ人が分かる。物音では Unidentified になる
    muffled: TextWithUnassignedPeople

@final
@dataclass(frozen=True)
class SightTextsDeclaration:                # 欄の意味は刺激の SightTexts (perception.md) と同じ。刺激を作るときに人を割り当てる
    clear: TextWithUnassignedPeople
    dim: TextWithUnassignedPeople | NotSeenInDim
    unseen_actor: TextWithUnassignedPeople | NotSeenWithoutActor
    noticed_later: TextWithUnassignedPeople | NotNoticedLater

@final
@dataclass(frozen=True)
class JointActionDeclaration:               # 二人で合わせる操作 (2 つの弁を 3 tick 以内に別々の人が開ける)
    joint_id: JointActionId
    required: tuple[tuple[ObjectId, InteractionId], ...]   # どの物体のどの操作か
    window: Ticks                           # 最初の操作の tick + window + 1 の tick に揃っていなければ時間切れ
    distinct_people: bool
    on_complete: Effect
    on_timeout: Effect                      # 最初の操作から window を過ぎた tick に 1 回だけ
    complete_notice: HappeningNotice | NoNotice
    timeout_notice: HappeningNotice | NoNotice

@final
@dataclass(frozen=True)
class ReactionDeclaration:
    reaction_id: ReactionId
    condition: Condition
    when_becomes_true: Effect
    when_becomes_false: Effect

@final
@dataclass(frozen=True)
class EndingDeclaration:
    ends_when: Condition

@final
@dataclass(frozen=True)
class WeatherDeclaration:
    initial: WeatherType
    changes: NoChange | ChangesEvery
    announce_changes: bool

    def next_after(self, current: WeatherState, roll: float) -> WeatherState: ...
    def obscures_sight(self, state: WeatherState) -> bool: ...   # 書かなければ嵐と霧
    def visibility(self, state: WeatherState) -> Visibility: ...
    def display_name(self, state: WeatherState) -> str: ...

@final
@dataclass(frozen=True)
class DayNightDeclaration:
    ticks_per_day: Ticks
    starts_at: TimeOfDay
    phases: tuple[DayPhaseDeclaration, ...]     # 1 日を切れ目なく覆う

@final
@dataclass(frozen=True)
class DayPhaseDeclaration:
    name: DayPhaseName
    begins_at: TimeOfDay
    dark: bool                                  # 書かなければ夜だけ真
    announcement: TextWithUnassignedPeople | NoAnnouncement

@final
@dataclass(frozen=True)
class ChangesEvery:
    ticks: Ticks
    transitions: WeatherTransitions        # 書かなければ既定の表

@final
@dataclass(frozen=True)
class WorldRules:
    tend: TendRule | NoTending              # NoTending なら介抱の行為が無い
    fatigue: FatigueRule
    hunger: HungerRule
    death: DeathRule
    departed_persons_act: bool
    hearing: HearingValues
    stealth: StealthRule
    action_durations: Mapping[ActionKind, Ticks]   # 行っているあいだの既定 (話すは行っているあいだを作らない)。話す・耳を澄ます 1、拾う・置く・渡す・区画・投票・持ち替え 1、操作・品物を使う 2、探す・介抱 3

@final
@dataclass(frozen=True)
class HearingValues:
    loudness: Mapping[Loudness, SoundLevel]     # ささやき 30、ふつう 60、大きい 75、とても大きい 90
    loss_per_passage: SoundLoss                 # 15
    clear_from: SoundLevel                      # 50
    muffled_from: SoundLevel                    # 35
    faint_from: SoundLevel                      # 20
    attentive_allowance: SoundLoss              # 耳を澄ますと 15 だけ小さい音まで聞こえる

    def level_of(self, loudness: Loudness) -> SoundLevel: ...
    def quietest_audible(self) -> SoundLevel: ...
    def quality(self, level: SoundLevel | NotReached, attentive: bool) -> HearingQuality: ...

@final
@dataclass(frozen=True)
class TendRule:
    revive_hp_rate: Rate                        # 0.6

@final
@dataclass(frozen=True)
class FatigueRule:
    per_exertion: FatigueAmount                 # 2
    limit: FatigueAmount                        # 100。達すると体を使う行為を断る (TooTired)
    levels: tuple[FatigueLevel, ...]            # 段階の境目と呼び名

@final
@dataclass(frozen=True)
class HungerRule:
    per_tick: HungerAmount                      # 1
    limit: HungerAmount
    starvation_damage: Damage | NoStarvationDamage   # 限界のあいだ毎 tick。NoStarvationDamage なら飢えても痛手が無い
    levels: tuple[HungerLevel, ...]

@final
@dataclass(frozen=True)
class DeathRule:
    grace: Ticks                                # 30。fell_at + grace の tick に死ぬ。0 なら倒れたらすぐ死ぬ

@final
@dataclass(frozen=True)
class StealthRule:                              # こっそり行っても、見ていた人ごとに確率で気づく
    notice_by_bystander: Mapping[SightQuality, Probability]   # SeesClearly 40%、SeesShapes 15%、SeesNothing 0%
    notice_by_target: Mapping[SightQuality, Probability]      # 60%、30%、0%
    attentive_bonus: Probability                # 耳を澄ましている人 +20%
    duration_rate: Multiplier                   # 行っているあいだを 2 倍
    # こっそり行った物音は 1 段小さくする。行った本人には、気づかれたかを伝えない

@final
@dataclass(frozen=True)
class Route:
    legs: tuple[PassageDeclaration, ...]

    @property
    def start(self) -> SpotId: ...
    @property
    def destination(self) -> SpotId: ...


class WorldDesign:
    @classmethod
    def compose(
        cls,
        nouns: DeclaredNouns,
        happenings: Iterable[HappeningDeclaration],
        reactions: Iterable[ReactionDeclaration],
        discoverables: Iterable[DiscoverableDeclaration],
        joint_actions: Iterable[JointActionDeclaration],
        person_interactions: Iterable[InteractionDeclaration],
        ending: EndingDeclaration,
        world_rules: WorldRules,
        weather: WeatherDeclaration | NoWeather,
        day_night: DayNightDeclaration | NoDayNight,
        initial_stage: WorldStageDeclaration | NoWorldStages,
    ) -> "WorldDesign": ...

    @property
    def nouns(self) -> DeclaredNouns: ...
    @property
    def world_rules(self) -> WorldRules: ...
    @property
    def ending(self) -> EndingDeclaration: ...

    def interaction_on_object(self, obj: ObjectId, interaction: InteractionId) -> InteractionDeclaration: ...
    def interaction_on_item(self, item_spec: ItemSpecId, interaction: InteractionId) -> InteractionDeclaration: ...
    def person_interaction(self, interaction: InteractionId) -> InteractionDeclaration: ...   # 殴る、盗むなど、人への操作
    def happenings(self) -> tuple[HappeningDeclaration, ...]: ...
    def joint_actions(self) -> tuple[JointActionDeclaration, ...]: ...
    def reactions(self) -> tuple[ReactionDeclaration, ...]: ...
    def discoverables_at(self, spot: SpotId) -> tuple[DiscoverableDeclaration, ...]: ...
    def route(self, start: SpotId, destination: SpotId) -> Route | NoRoute: ...
    def initial_world(self) -> InitialWorld: ...
    def warnings(self) -> tuple[DesignWarning, ...]: ...


@final
@dataclass(frozen=True)
class DesignFlaw:                           # 読み込みを止める
    location: DesignLocation
    reason: str

@final
@dataclass(frozen=True)
class DesignWarning:                        # 読み込みは続ける
    location: DesignLocation
    reason: str

class WorldDesignFlawsException(WorldDesignException):
    flaws: tuple[DesignFlaw, ...]
```

## 作る順

```
infrastructure: JSON を読む
  ① 名詞の宣言を作る → DeclaredNouns
  ② 動詞の宣言 (条件、効果、操作、出来事) を、DeclaredNouns から名詞を引いて作る
  ③ WorldDesign.compose
```

- 誤りは最初の 1 つで止めず、集めてから 1 つの `WorldDesignFlawsException` で投げる。どの誤りにも場所 (`DesignLocation`) を付ける。JSON の書き方の誤り (必須キーの欠け、列挙の綴り違い) も infrastructure が `DesignFlaw` に包み、素の `KeyError` / `ValueError` を外に出さない
- compose は、条件と効果を置いた場所ごとに使える主語 ([condition.md](condition.md)) と、`requirements()` を照らし合わせる
- `initially_raised` でもなく、どの `RaiseFlagEffect` にも出てこない旗を条件が見ていたら `DesignFlaw`。立てるだけで誰も見ない旗は `DesignWarning`
- 締める出来事 (`CloseGroupDecisionEffect`) が 1 つも無い集団の決定は `DesignWarning`。猶予 (`DeathRule.grace`) が 0 なのに介抱がある世界は `DesignFlaw`
- 作者が書かなかった知覚の文 (目撃の文、された人の文、音の文、起きてから気づく文) は、compose が決まった文で埋め、`DesignWarning` を残す。倒れていた本人が起きてから気づく文だけは、書かなければ気づかない (`NotNoticedLater`)
- 宣言に無い通路の状態の名前、呼び名 (`display_name`) の無い値が文に出るときは、`DesignFlaw` で止める
