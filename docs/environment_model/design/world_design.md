# 設計図 (WorldDesign)

シナリオが宣言したもの。run の間は変わらない。

場所を指す `SpotId` は、シナリオが宣言した場所の名前 (`"lift_landing"`) を持つ。連番の数は振らない (D1982)。

エージェントに見せる名前・呼び名・操作の言葉は `DisplayName` (空でない 1 行)、説明・見た目・物音・匂いは `DescriptionText` (空でない。改行はあってよい) で持つ。空の名前の品物が「が落ちている」と出たり、改行の入った名前ができることの一覧を崩したりするのを、宣言を作るときに止める。長さの上限は、困る場面が出るまで付けない。人のプレースホルダーを持つ文は `TextWithUnassignedPeople`。

名詞の宣言は、その名詞が何であるか (名前、置き場所、見た目、状態) だけを持ち、条件・効果・操作・知覚の宣言を持たない。名詞に付く動詞は、名詞の宣言を指す動詞の側の宣言 (`ObjectInteractionDeclaration` など) に置く。条件と効果は名詞の宣言を持つので、名詞が動詞を持つと、互いを指す仕掛け (レバーが扉を現し、扉がレバーの覆いを外す) や自分を指す仕掛け (籠の中にいる人は籠に入れない) を、値の変わらない型で作れなくなる。名詞を全部作ってから動詞を作れば、どの組み合わせも作れる。シナリオの作者は物の欄の中に操作を書いてよく、読み込む側が名詞と動詞に分けて組み立てる。

```python
# 名詞の宣言

@final
@dataclass(frozen=True)
class FlagDeclaration:
    flag_id: FlagId
    meaning: DescriptionText
    initially_raised: bool

@final
@dataclass(frozen=True)
class SpotDeclaration:
    spot_id: SpotId
    name: DisplayName
    description: DescriptionText
    atmosphere: SpotAtmosphere

class Temperature(Enum):                    # 寒い順。比べられる
    FREEZING
    COLD
    NORMAL
    WARM
    HOT

@final
@dataclass(frozen=True)
class SpotAtmosphere:
    lighting: Lighting
    outdoor: bool                           # 明るさの計算の材料 (LightingConditions.outdoor)
    temperature: Temperature
    ambient_sound: DescriptionText | NoAmbientSound
    smell: DescriptionText | NoSmell

    def with_changes(
        self,
        lighting: Lighting | Unchanged,
        temperature: Temperature | Unchanged,
        ambient_sound: DescriptionText | NoAmbientSound | Unchanged,
        smell: DescriptionText | NoSmell | Unchanged,
    ) -> "SpotAtmosphere": ...

@final
@dataclass(frozen=True)
class SpotSectionDeclaration:               # 場所の中の、体で入る一角 (籠の中、小舟、檻、見張り台)。中と外は同じ場所
    section_id: SpotSectionId
    spot_id: SpotId
    name: DisplayName
    capacity: Capacity | NoCapacity
    reachable_objects: tuple[ObjectId, ...] # 中からしか届かない物

@final
@dataclass(frozen=True)
class PassageDeclaration:
    passage_id: PassageId
    ends: tuple[SpotId, SpotId]
    two_way: bool
    travel_ticks: Ticks
    states: tuple[PassageStateDeclaration, ...]   # 書かなければ open (「開いている」、通れる、減衰 0) の 1 つ
    initial_state: PassageStateName               # 書かなければ open

    def allows(self, state: PassageStateName) -> bool: ...
    def state(self, name: PassageStateName) -> PassageStateDeclaration: ...

@final
@dataclass(frozen=True)
class PassageStateDeclaration:
    name: PassageStateName
    display_name: DisplayName
    traversable: bool
    sound_loss: SoundLoss

@final
@dataclass(frozen=True)
class ObjectStateKeyDeclaration:
    object_id: ObjectId
    key: StateKeyId
    kind: StateKind
    initial: StateValue                     # kind.accepts(initial) でなければ作れない。書いた文の鍵は NothingWritten だけ

StateKind = ItemStateKind | StockStateKind | WrittenTextStateKind
ItemStateKind = FlagStateKind | CountStateKind | ChoiceStateKind   # 品物は在庫と書いた文を持たない
FlagStateKind()
CountStateKind()                            # 上限を持たない
ChoiceStateKind(choices: tuple[ChoiceName, ...])     # 1 つ以上、重ならない
StockStateKind(capacity: Count, refills_every: Ticks | NoRefill)   # 上限・間隔ともに 1 以上
WrittenTextStateKind()
# どの種類も accepts(value: StateValue) -> bool を持つ

StateValue = FlagValue | CountValue | ChoiceValue | StockValue | WrittenText | NothingWritten
FlagValue(raised: bool)
CountValue(count: Count)
ChoiceValue(choice: ChoiceName)
StockValue(amount: Count)
WrittenText(body: TextBody, author: PersonId, written_at: WorldTick)
NothingWritten()

@final
@dataclass(frozen=True)
class ItemStateKeyDeclaration:
    item_spec_id: ItemSpecId
    key: StateKeyId
    kind: ItemStateKind
    initial: StateValue

@final
@dataclass(frozen=True)
class ObjectDeclaration:
    object_id: ObjectId
    spot_id: SpotId
    name: DisplayName
    description: DescriptionText
    appearance: ObjectAppearance
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
    name: DisplayName
    description: DescriptionText
    state_keys: tuple[ItemStateKeyDeclaration, ...]
    lights_up: LitWhen | NotALightSource     # LitWhen(key, value): その状態の値のとき灯っている。手に持っているあいだ場所を照らす
    hands_needed: HandsNeeded                # 1 (カンテラ) / 2 (つるはし)。書かなければ 1

@final
@dataclass(frozen=True)
class GroupDeclaration:
    group_id: GroupId
    grouping: GroupingDeclaration
    name: DisplayName
    members_know_each_other: bool
    shared_description: DescriptionText | NoSharedDescription

    def members_can_change(self) -> bool: ...

@final
@dataclass(frozen=True)
class GroupingDeclaration:
    grouping_id: GroupingId
    name: DisplayName
    visibility: MembershipVisibility        # EVERYONE / SELF_ONLY / NOBODY
    changes: bool

@final
@dataclass(frozen=True)
class CharacterDeclaration:
    person_id: PersonId                      # 人柄 (Persona) は持たない。Being が自分の人柄を持って入る (D1928-3)。シナリオの登場人物の欄は、読み込む側が世界の部分と Being の人柄に分ける
    appearance: DescriptionText
    spawn_spot: SpotId
    initial_items: tuple[ItemSpecId, ...]    # 同じ品物を 2 回書けば 2 つ持つ
    initial_held: tuple[ItemSpecId, ...]     # initial_items のうち、最初から手に持っている物。品物ごとに initial_items の数を超えられない
    initial_groups: tuple[GroupId, ...]      # 重ならない
    knows_at_start: tuple[PersonId, ...]     # 重ならない。自分を含んでもよい

@final
@dataclass(frozen=True)
class WorldStageDeclaration:
    stage_id: WorldStageId
    name: DisplayName
    description: DescriptionText
    allowed_actions: frozenset[ActionKind | InteractionId] | AllActionsAllowed

@final
@dataclass(frozen=True)
class GroupDecisionDeclaration:
    decision_id: GroupDecisionId
    name: DisplayName
    abstain_allowed: bool
    reveals_ballots: bool                   # 集計のとき、誰が誰に入れたかを知らせるか

@final
@dataclass(frozen=True)
class OutcomeDeclaration:
    outcome_id: OutcomeId
    name: DisplayName                               # 「救出」
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

# 名詞に付く動詞。名詞の宣言を指す

@final
@dataclass(frozen=True)
class ObjectInteractionDeclaration:
    obj: ObjectDeclaration
    interaction: InteractionDeclaration

@final
@dataclass(frozen=True)
class ItemInteractionDeclaration:
    item_spec: ItemSpecDeclaration
    interaction: InteractionDeclaration

@final
@dataclass(frozen=True)
class ItemUseDeclaration:                   # 宣言の無い品物は使えない (NotUsable)
    item_spec: ItemSpecDeclaration
    effect: Effect

@final
@dataclass(frozen=True)
class SectionAccessDeclaration:             # 区画への出入り。区画ごとに必ず 1 つ。無ければ DesignFlaw
    section: SpotSectionDeclaration
    enter_label: DisplayName                        # 「籠に乗り込む」
    leave_label: DisplayName                        # 「籠から降りる」
    enter_text: TextWithUnassignedPeople    # 入った本人の体の刺激
    leave_text: TextWithUnassignedPeople
    exertion: Exertion
    duration: Ticks | DefaultDuration
    entry_condition: Condition              # 書かなければ、いつでも入れる
    perceived_as: PerceptionDeclaration

@final
@dataclass(frozen=True)
class PassageTraversalDeclaration:          # 宣言の無い通路は、状態が通れればいつでも通れる
    passage: PassageDeclaration
    condition: Condition

@final
@dataclass(frozen=True)
class WorldStageEffectsDeclaration:         # 宣言の無い段階は、出入りで何も起きない
    stage: WorldStageDeclaration
    when_entered: Effect
    when_left: Effect

@final
@dataclass(frozen=True)
class GroupDecisionRulesDeclaration:        # 集団の決定ごとに必ず 1 つ。無ければ DesignFlaw
    decision: GroupDecisionDeclaration
    voters: PeopleSelection
    choices: PeopleSelection
    when_decided: Effect
    when_undecided: Effect

# 1 つの名詞に同じ種類の宣言が 2 つあれば DesignFlaw (ObjectInteractionDeclaration と ItemInteractionDeclaration は、同じ操作の名前が 2 つあれば)

@final
@dataclass(frozen=True)
class InteractionDeclaration:
    interaction_id: InteractionId
    display_label: DisplayName
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
    obscuring: frozenset[WeatherType]       # 見通しの悪い天候。書かなければ嵐と霧

    def next_after(self, current: WeatherState, roll: Probability) -> WeatherState: ...
    def obscures_sight(self, state: WeatherState) -> bool: ...
    def display_name(self, state: WeatherState) -> DisplayName: ...   # 種類ごとに決まった呼び名 (晴れ、霧 など)

class WeatherType(Enum):                    # CLEAR / CLOUDY / RAIN / HEAVY_RAIN / SNOW / BLIZZARD / FOG / STORM
WeatherState(type: WeatherType)             # 今の天候。強さは持たない

@final
@dataclass(frozen=True)
class DayNightDeclaration:
    ticks_per_day: Ticks
    starts_at: TimeOfDay
    phases: tuple[DayPhaseDeclaration, ...]     # 1 日を切れ目なく覆う。begins_at の昇順で、名前は重ならない。最初の段階より前は前の日の最後の段階が続く

    def time_of_day_at(self, now: WorldTick) -> TimeOfDay: ...   # (starts_at + now) を ticks_per_day で割った余り
    def phase_at(self, time_of_day: TimeOfDay) -> DayPhaseDeclaration: ...

TimeOfDay(tick_of_day: int)                 # 1 日の中の tick の位置。ticks_per_day 未満

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
    # WeatherTransitions(odds: tuple[NextWeatherOdds, ...]): 今の天候ごとに、次の天候と 1 以上の重み (WeightedWeather) の見込み。roll で重みの累積から選ぶ。見込みの無い天候は変わらない

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
    # loudness が 4 段階すべてを持ち、clear_from ≥ muffled_from ≥ faint_from でなければ作れない

    def level_of(self, loudness: Loudness) -> SoundLevel: ...
    def quietest_audible(self) -> SoundLevel: ...
        # faint_from − attentive_allowance (0 で止まる)。spread の stop_below に渡し、耳を澄ました人に届く音を途中で切らない
    def quality(self, level: SoundLevel | NotReached, attentive: bool) -> HearingQuality: ...
        # 耳を澄ましていれば、3 つの境目をすべて attentive_allowance だけ下げて比べる。境目ちょうどはその段階に入る

@final
@dataclass(frozen=True)
class TendRule:
    revive_hp_rate: Rate                        # 0.6

@final
@dataclass(frozen=True)
class FatigueRule:
    per_exertion: FatigueAmount                 # 2。0 なら疲れない世界
    limit: FatigueAmount                        # 100。1 以上。疲れはここで止まる。達すると体を使う行為を断る (TooTired)
    levels: tuple[FatigueLevel, ...]            # 段階の境目と呼び名。1 つ以上、最初の境目は 0、境目は狭義の昇順で limit 以下、呼び名は重ならない

    def level_of(self, amount: FatigueAmount) -> FatigueLevel: ...   # 境目に達した段階のうち、いちばん境目の大きい段階

@final
@dataclass(frozen=True)
class FatigueLevel:
    starts_at: FatigueAmount
    name: FatigueLevelName                      # 空でない呼び名

@final
@dataclass(frozen=True)
class HungerRule:
    per_tick: HungerAmount                      # 1。0 なら腹が減らない世界
    limit: HungerAmount                         # 1 以上。空腹はここで止まる
    starvation_damage: Damage | NoStarvationDamage   # 限界のあいだ毎 tick。NoStarvationDamage なら飢えても痛手が無い
    levels: tuple[HungerLevel, ...]             # FatigueRule.levels と同じ決まり

    def level_of(self, amount: HungerAmount) -> HungerLevel: ...

@final
@dataclass(frozen=True)
class HungerLevel:
    starts_at: HungerAmount
    name: HungerLevelName                       # 空でない呼び名

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
        object_interactions: Iterable[ObjectInteractionDeclaration],
        item_interactions: Iterable[ItemInteractionDeclaration],
        item_uses: Iterable[ItemUseDeclaration],
        section_accesses: Iterable[SectionAccessDeclaration],
        passage_traversals: Iterable[PassageTraversalDeclaration],
        world_stage_effects: Iterable[WorldStageEffectsDeclaration],
        group_decision_rules: Iterable[GroupDecisionRulesDeclaration],
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
    def interactions_on_object(self, obj: ObjectId) -> tuple[InteractionDeclaration, ...]: ...
    def interactions_on_item(self, item_spec: ItemSpecId) -> tuple[InteractionDeclaration, ...]: ...
    def use_of_item(self, item_spec: ItemSpecId) -> ItemUseDeclaration | NotUsable: ...
    def section_access(self, section: SpotSectionId) -> SectionAccessDeclaration: ...
    def passage_traversal(self, passage: PassageId) -> Condition: ...                   # 宣言が無ければ、いつでも真の条件
    def world_stage_effects(self, stage: WorldStageId) -> WorldStageEffectsDeclaration: ...
    def group_decision_rules(self, decision: GroupDecisionId) -> GroupDecisionRulesDeclaration: ...
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
  ② 動詞の宣言 (名詞に付く動詞、条件、効果、操作、出来事) を、DeclaredNouns から名詞を引いて作る
  ③ WorldDesign.compose
```

- 名詞の宣言は互いを宣言ではなく ID で指す (`SpotSectionDeclaration.reachable_objects`、`CharacterDeclaration.spawn_spot` など)。ID が宣言にあるかは `DeclaredNouns` が作るときに確かめ、無ければ `DesignFlaw` にする。`GroupDeclaration.grouping` だけは、分け方が集団を指さず循環しないので、宣言のまま持つ
- `DeclaredNouns` は ID の有無のほかに、次も照らし合わせて `DesignFlaw` にする (#1995)。集まりの持つ分け方が `groupings` に無いか、同じ `grouping_id` の宣言と中身が違う (`groups_in` が返せなくなる)。区画の `reachable_objects` の物が区画と違う場所にある。登場人物の `initial_groups` に同じ分け方の集まりが 2 つある (`group_of` は 1 つしか返せない)
- 宣言 1 つだけで判断できる誤り (通路の状態名の重複、両端が同じ場所の通路、`initial_state` が `states` に無い、区画の `reachable_objects` の重複、状態の鍵の重複、種類に合わない `initial`) は、宣言の型が作るときにドメイン例外で断る。ほかの宣言と照らし合わせて分かる誤りは `DeclaredNouns` が確かめる。どちらで止めても作者に返るのは `DesignFlaw` で、宣言の型の例外は読み込む側が場所を付けて `DesignFlaw` に包む
- `Unchanged` (雰囲気を変える効果で、変えない欄) と `NoCapacity` (区画の定員が無い) は、中身の無い型

- 誤りは最初の 1 つで止めず、集めてから 1 つの `WorldDesignFlawsException` で投げる。どの誤りにも場所 (`DesignLocation`) を付ける。JSON の書き方の誤り (必須キーの欠け、列挙の綴り違い) も infrastructure が `DesignFlaw` に包み、素の `KeyError` / `ValueError` を外に出さない
- compose は、条件と効果を置いた場所ごとに使える主語 ([condition.md](condition.md)) と、`requirements()` を照らし合わせる
- `initially_raised` でもなく、どの `RaiseFlagEffect` にも出てこない旗を条件が見ていたら `DesignFlaw`。立てるだけで誰も見ない旗は `DesignWarning`
- 締める出来事 (`CloseGroupDecisionEffect`) が 1 つも無い集団の決定は `DesignWarning`。猶予 (`DeathRule.grace`) が 0 なのに介抱がある世界は `DesignFlaw`
- 作者が書かなかった知覚の文 (目撃の文、された人の文、音の文、起きてから気づく文) は、compose が決まった文で埋め、`DesignWarning` を残す。倒れていた本人が起きてから気づく文だけは、書かなければ気づかない (`NotNoticedLater`)
- 宣言に無い通路の状態の名前、呼び名 (`display_name`) の無い値が文に出るときは、`DesignFlaw` で止める
