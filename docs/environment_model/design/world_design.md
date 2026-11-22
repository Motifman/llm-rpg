# 設計図 (WorldDesign)

シナリオが宣言したもの。run の間は変わらない。

場所を指す `SpotId` は、シナリオが宣言した場所の名前 (`"lift_landing"`) を持つ。連番の数は振らない (D1982)。

エージェントに見せる名前・呼び名・操作の言葉は `DisplayName` (空でない 1 行)、説明・見た目・物音・匂いは `DescriptionText` (空でない。改行はあってよい) で持つ。空の名前の品物が「が落ちている」と出たり、改行の入った名前ができることの一覧を崩したりするのを、宣言を作るときに止める。長さの上限は、困る場面が出るまで付けない。人のプレースホルダーを持つ文は `TextWithUnassignedPeople`。

宣言の型は既定値を持たない。欄のコメントの「書かなければ」は、シナリオを読み込む側が埋める (既定の文や値は、コードではなくデータとして取り込む)。

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
    allows_shops: bool                      # 人が店を出せる場所か。書かなければ偽 (共通の部品の defaults.spot) (D2224)

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
    name: DisplayName                             # 場面で通路を指すときの名前 (「古い梯子」)
    description: DescriptionText                  # 名前だけでは分からない通路の様子。どちらも書き忘れは DesignFlaw で、既定で埋めない
    ends: tuple[SpotId, SpotId]
    two_way: bool
    travel_ticks: Ticks
    states: tuple[PassageStateDeclaration, ...]   # 1 つ以上。書かなければ読み込む側が共通の部品の defaults.passage で埋める
    initial_state: PassageStateName
    hidden_until_revealed: bool                   # RevealPassageEffect までは無い道

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

    def require_fits(self, value: StateValue) -> None: ...   # kind.accepts(value) でなければ StateValueMismatchesKindException
    def require_count(self) -> None: ...                     # 数の鍵でなければ StateKeyOfAnotherKindException。require_stock・require_written_text も同じ形

StateKind = ItemStateKind | StockStateKind | WrittenTextStateKind
ItemStateKind = FlagStateKind | CountStateKind | ChoiceStateKind   # 品物は在庫と書いた文を持たない
FlagStateKind()
CountStateKind()                            # 上限を持たない
ChoiceStateKind(choices: tuple[ChoiceName, ...])     # 1 つ以上、重ならない
StockStateKind(capacity: Count, refills_every: Ticks | NoRefill)   # 上限・間隔ともに 1 以上
WrittenTextStateKind()
# どの種類も accepts(value: StateValue) -> bool と holds_written_text() -> bool (書いた文を持つ種類か。WrittenTextStateKind だけが真) を持つ
# holds_count() -> bool は CountStateKind だけ、holds_stock() -> bool は StockStateKind だけが真

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

    def require_fits(self, value: StateValue) -> None: ...   # kind.accepts(value) でなければ StateValueMismatchesKindException

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
    hands_needed: HandsNeeded                # 1 (カンテラ) / 2 (つるはし)
    lasts: Lasts | LastsIndefinitely         # 書かなければ LastsIndefinitely。共通の部品に既定は置かない (#2068)

@final
@dataclass(frozen=True)
class Lasts:                                # 世界に出てから ticks で、荷・手・地面のどこにあっても世界から消える (カンテラの灯、たいまつ)
    ticks: Ticks                            # 1 以上
    ended_text: DescriptionText             # 持っていた本人と、地面にあればその場所で見えていた人に届く文。消えたあと何も残さない

    def has_run_out(self, age: Ticks) -> bool: ...   # age が ticks 以上か。LastsIndefinitely はいつも偽

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
    person_id: PersonId                      # 人柄 (Persona)、この世界での立場、本人の目的は持たない。Being が自分の人柄を持って入る (D1928-3)。立場と目的は、読み込む側が人ごとに入るときに渡す文 (CharacterBriefing) にして世界の宣言の外に返す (D2222)
    appearance: DescriptionText
    spawn_spot: SpotId
    initial_items: tuple[ItemSpecId, ...]    # 同じ品物を 2 回書けば 2 つ持つ
    initial_held: tuple[ItemSpecId, ...]     # initial_items のうち、最初から手に持っている物。品物ごとに initial_items の数を超えられない。hands_needed の合計は人の手の数 (2) を超えられない
    initial_groups: tuple[GroupId, ...]      # 重ならない
    knows_at_start: tuple[PersonId, ...]     # 重ならない。自分を含んでもよい
    max_hp: HitPoints | UsesWorldDefault     # UsesWorldDefault なら WorldRules.person_max_hp で始まる (#2055)
    pack_capacity: Capacity | UsesWorldDefault   # UsesWorldDefault なら WorldRules.pack_capacity
    initial_gold: Gold                       # 初めの所持金。書かなければ 0 (共通の部品の defaults.character) (D2224)

    def starting_hp(self, world_default: HitPoints) -> HitPoints: ...
    def starting_pack_capacity(self, world_default: Capacity) -> Capacity: ...

@final
@dataclass(frozen=True)
class WorldStageDeclaration:
    stage_id: WorldStageId
    name: DisplayName
    description: DescriptionText
    allowed_actions: frozenset[ActionKind | InteractionId] | AllActionsAllowed

    def allows(self, kind: ActionKind) -> bool: ...                       # 組み込みの行為
    def allows_interaction(self, interaction: InteractionId) -> bool: ... # 作者の操作。INTERACT_WITH_* の ActionKind では許さない

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
    announcement: TextWithUnassignedPeople # 「{each_person}は昇降機で外へ出た。」結末が決まった本人だけに、世界から外れていても、目立つ世界の知らせとして届ける。死んだ結末には知らせが無い (D2203)

@final
@dataclass(frozen=True)
class ScenarioShopDeclaration:              # 作者が持ち主の店 (D2224)。人の店と同じ Shop 集約になり、エージェントは同じ行為で売り買いする
    shop_id: ScenarioShopId
    spot_id: SpotId                         # 店を出せる場所 (allows_shops) でなくてよい
    keeper_name: DisplayName                # 持ち主の呼び名 (「グスタフ」)。世界の人ではないので、名前を文字のまま出す
    look: ShopLook
    selling: tuple[ScenarioShopLineDeclaration, ...]
    buying: tuple[ScenarioShopLineDeclaration, ...]
    gold: Gold | UnlimitedSupply            # 買い取りに払うお金。売れた代金はここに足す

@final
@dataclass(frozen=True)
class ScenarioShopLineDeclaration:
    item_spec: ItemSpecId
    count: Count | UnlimitedSupply          # 売りは在庫、買い取りは買い取る数。尽きない (UnlimitedSupply) と書ける
    unit_price: Gold
    note: ShopLineNote | NoNote
    # 売りと買い取りのそれぞれで、同じ品物の種類を 2 つ書けば作れない


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
        monster_specs: Iterable[MonsterSpecDeclaration],     # monster.md
        monster_spawns: Iterable[MonsterSpawnDeclaration],
        scenario_shops: Iterable[ScenarioShopDeclaration],   # D2224
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
    def world_stage_of(self, stage: WorldStageId) -> WorldStageDeclaration: ...   # 実行時に集約が持つ ID から引く
    def object_of(self, obj: ObjectId) -> ObjectDeclaration: ...
    def group_decision(self, name: str, at: DesignLocation) -> GroupDecisionDeclaration: ...
    def section(self, name: str, at: DesignLocation) -> SpotSectionDeclaration: ...
    def sections_at(self, spot: SpotId) -> tuple[SpotSectionDeclaration, ...]: ...
    def outcome(self, name: str, at: DesignLocation) -> OutcomeDeclaration: ...
    def monster_spec(self, name: str, at: DesignLocation) -> MonsterSpecDeclaration: ...
    def monster_spawn(self, name: str, at: DesignLocation) -> MonsterSpawnDeclaration: ...
    def scenario_shops(self) -> tuple[ScenarioShopDeclaration, ...]: ...
    def has_shops(self) -> bool: ...   # 店を出せる場所か作者の店が 1 つでもあるか。無ければ店の行為をツールの一覧から消す (ToolExposure)
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
class ObjectLooksDeclaration:               # 物の見え方。条件を持つので名詞ではなく動詞の側に置く。宣言の無い物は見え方を持たない (#2067、#2070)
    object_id: ObjectId
    looks: tuple[ObjectLook, ...]           # 書いた順に確かめ、最初に当てはまった 1 つの文を説明に続けて場面に出す

    def look_now(self, facts: WorldFacts) -> DescriptionText | NoLook: ...
        # 条件はきっかけ LookingAround で確かめる。どれにも当てはまらなければ NoLook で、場面には説明だけが出る

@final
@dataclass(frozen=True)
class ObjectLook:                           # 「この条件のときはこう見える」(水門が開いていれば「開いていて、水の流れる音がする」)
    when: Condition
    text: DescriptionText

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
    arguments: tuple[ArgumentDeclaration, ...]   # エージェントが渡す引数。効果と条件が読む引数の名前はここに無ければならない

@final
@dataclass(frozen=True)
class ArgumentDeclaration:
    name: ArgumentName
    kind: TextArgument | ItemArgument       # TextArgument: 文 (書く内容、合言葉) / ItemArgument: 場面に見えている品物から 1 つ

@final
@dataclass(frozen=True)
class DiscoverableDeclaration:
    discoverable_id: DiscoverableId
    spot_id: SpotId
    found_text: TextWithUnassignedPeople   # 見つけた本人の体の刺激になる
    condition: Condition
    when_found: Effect
    finding: Finding                         # ONCE_IN_WORLD: 誰かが見つけたら終わり / ONCE_PER_PERSON: 人ごとに 1 回

ShownToActor = PeopleCountAt | WrittenTextOf   # 成功したとき本人だけに見せる、世界の今の値。success_text の後ろに付ける
PeopleCountAt(spot: SpotDeclaration)
WrittenTextOf(key: ObjectStateKeyDeclaration)

@final
@dataclass(frozen=True)
class HappeningDeclaration:
    happening_id: HappeningId
    condition: Condition
    effect: Effect
    once: bool                              # 断られた回も「起きた」に数える。once の出来事は、断られたら以後は起きない
    notice: HappeningNotice | NoNotice      # AnnouncementTo の相手は、その出来事の効果を当てる前の世界で選ぶ
    # 知らせ (SightAt / SoundFrom / AnnouncementTo) の文には人のプレースホルダーを書けない。出来事には行った人がおらず当てる人がいないので、書けば読み込みで止める (二人で合わせる操作の知らせも同じ) (#2152)

HappeningNotice = SightAt | SoundFrom | AnnouncementTo
# 発火で集約が断ったら (WorldRefusal)、その発火だけを巻き戻し、何も変えずに「その回は起きた」と記録する。
# 次の tick に試し直さない。周期の出来事は書いた間隔のまま動き、確実に通したい 1 回きりの出来事は、作者が条件に書く (「荷が空いていれば」)

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
class NoticedOnWaking:                      # 倒れていた相手が、目が覚めてから気づく文。倒れている相手には行為の最中の文 (clear など) が届かない (#2076)
    text: TextWithUnassignedPeople

@final
@dataclass(frozen=True)
class PerceptionDeclaration:                # 行為が周りにどう知覚されるか
    witness: SightTextsDeclaration
    target: SightTextsDeclaration | NoticedOnWaking | NoTarget   # NoticedOnWaking は相手が倒れている組み込みの行為 (介抱) だけ
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
    distinct_people: bool                   # 部分ごとに最後に行った人が全員違うときだけ揃う。押し直しても窓は延ばさない (D2173)
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
    when_becomes_false: Effect               # 断られても新しい真偽を記録し、同じ真偽のあいだは試し直さない

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
    def weather_after(self, now: WorldTick, current: WeatherState, random: RandomSource) -> WeatherState: ...
        # ChangesEvery(ticks=N) なら、時計が進んだあとの時刻が N の倍数 (tick 0 から数えて N, 2N, ...) のときだけ random から 1 回引いて next_after で選ぶ。それ以外の時刻と NoChange では引かずに今の天候を返す
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
    def day_and_clock_time_at(self, now: WorldTick) -> DayAndClockTime: ...   # 1 日 = 24 時間として割り当て、分は切り捨てる。世界が始まった日が 1 日目。NoDayNight では NotDeclaredInThisWorldException (D2222)

TimeOfDay(tick_of_day: int)                 # 1 日の中の tick の位置。ticks_per_day 未満
DayAndClockTime(day: int, hour: int, minute: int)   # 何日目と時:分。day は 1 から

@final
@dataclass(frozen=True)
class DayPhaseDeclaration:
    name: DayPhaseName
    begins_at: TimeOfDay
    dark: bool                                  # 書かなければ夜だけ真
    announcement: TextWithUnassignedPeople | NoAnnouncement
    audience: PeopleSelection | EveryoneAwake   # 知らせの届く相手。EveryoneAwake なら起きている全員。どちらでも倒れている人には届けず、ためもしない (D2203)

@final
@dataclass(frozen=True)
class EveryoneAwake: ...                        # 倒れていない全員。死んで去った人として動く人と移動中の人を含み、結末が決まって世界から外れた人は含まない (D2203)

@final
@dataclass(frozen=True)
class ChangesEvery:
    ticks: Ticks
    transitions: WeatherTransitions        # 書かなければ既定の表
    def weather_at(self, now: WorldTick, current: WeatherType, random: RandomSource) -> WeatherType: ...
        # now が ticks の倍数のときだけ random から 1 回引いて transitions で選ぶ。NoChange.weather_at は引かずに current を返す
    # WeatherTransitions(odds: tuple[NextWeatherOdds, ...]): 今の天候ごとに、次の天候と 1 以上の重み (WeightedWeather) の見込み。roll で重みの累積から選ぶ。見込みの無い天候は変わらない

@final
@dataclass(frozen=True)
class WorldRules:
    tend: TendRule | NoTending              # NoTending なら介抱の行為が無い
    fatigue: FatigueRule
    hunger: HungerRule
    death: DeathRule
    departed_persons_act: bool
    name_tags: bool                         # 名札の世界。真なら、見る人は知り合いでなくても相手の名前が分かる
    hearing: HearingValues
    stealth: StealthRule
    action_durations: Mapping[ActionKind, Ticks]   # 行っているあいだの既定。耳を澄ます 1、拾う・置く・渡す・区画・投票・持ち替え 1、操作・品物を使う 2、探す・介抱 3
    # 移動は通路の時間で決まり、待つこと・話すこと・モンスターへの攻撃は行っているあいだを作らない (#1971)
    # 店の行為 (開く・閉じる・品目を編集する・見た目を書き直す・買う・売る・引き取る) は 1 (D2224)
    # action_durations は上の 22 種類をすべて持ち、移動・待つ・話す・モンスターへの攻撃を持たなければ作れない
    person_max_hp: HitPoints                # 人の最初の体力の世界の既定。登場人物が上書きできる (#2055)
    pack_capacity: Capacity                 # 荷に持てる数の世界の既定
    person_attack_damage: Damage            # 人がモンスターに与える痛手。共通の部品の既定 10。武器・防御・命中は持たない (#1971)

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
    duration_multiplier: Multiplier             # 行っているあいだを 2 倍
    # こっそり行った物音は 1 段小さくする。行った本人には、気づかれたかを伝えない
    # notice_by_bystander と notice_by_target が SightQuality の 3 つすべてを持たなければ作れない

@final
@dataclass(frozen=True)
class BuiltInActionPerceptions:             # どの世界にもある行為 (拾う、置く、渡す、移動する、話すなど) が周りにどう知覚されるか。シナリオが世界全体で 1 つ書く
    by_kind: Mapping[ActionKind, PerceptionDeclaration]   # SPEAK は持たない (声の大きさごとに下の 3 つ)
    whisper: PerceptionDeclaration
    ordinary_voice: PerceptionDeclaration
    shout: PerceptionDeclaration
    arrival: PerceptionDeclaration          # 着いた場所にいた人へ。行為ではなく OccupantEnteredSpotEvent から作り、着いた本人には届けない (#2061)
    item_joiner: ItemNameJoiner             # 渡す行為で品物が 2 つ以上のとき、{item} の呼び名をつなぐ言葉 (共通の部品では「と」)。1 つのときは使わない。書かなければ読み込みで止める。つなぐ言葉をコードに持たないため (#2152)
    gold_label: GoldLabel                   # お金の呼び名 (共通の部品では「{amount}G」)。渡す行為では、お金を品物の後ろに item_joiner でつないで {item} に入れる。店の文の {gold} にも使う (D2224)

    def speech(self, reach: Whisper | OrdinaryVoice | Shout) -> PerceptionDeclaration: ...
    def rows(self) -> tuple[tuple[BuiltInPerceptionRow, PerceptionDeclaration], ...]: ...
    # 各行の文は、その行の BuiltInPerceptionRow.nameable にある呼び名だけを書ける。相手のいない行に相手が見る文 (target) を書けば作れない
    # 文には人のプレースホルダーのほかに、行為が扱う物や場所の呼び名 ({item}、{destination} など) を書ける。
    # 刺激に変える役が宣言の呼び名 (DisplayName) で先に埋め、人のプレースホルダーだけを残した TextAboutPeople にする
    # 操作 (INTERACT_WITH_*)・区画の出入り (ENTER_SECTION / LEAVE_SECTION) は宣言の perceived_as で知覚されるので、書けば作れない (D2026)
    # モンスターへの攻撃 (ATTACK_MONSTER) は表の行に持ち、{monster} を書ける (#1971、monster.md)
    # どの行にも世界の知らせ (announcement) は書けない。知らせの相手は行為の前の世界で選ぶもので、組み込みの行為には選ぶところが無く、書いても届かないため。書けば作れない (#2152)

@final
@dataclass(frozen=True)
class BuiltInPerceptionRow:                 # 組み込みの行為の知覚の表の 1 行。その行為に相手がいるかと、文に書ける呼び名を 1 か所で決める (#2076)
    name: str                               # ActionKind の名前 (PICK_UP など)、または whisper / speak / shout / arrival
    has_target: bool                        # 渡す・介抱する・ささやくだけ相手がいる
    target_is_down: bool                    # 介抱だけ真。相手の文は NoticedOnWaking だけを持て、書かなければ気づかない (NoTarget)
    names_of_things: frozenset[str]         # 人のほかに書ける呼び名 ({item}、{destination}、{speech}、{origin})

    @classmethod
    def of_kind(cls, kind: ActionKind) -> "BuiltInPerceptionRow": ...
    @classmethod
    def kinds(cls) -> frozenset[ActionKind]: ...   # by_kind に書ける行為の種類
    # whisper()、speak()、shout()、arrival() も同じく行を返す
    @property
    def nameable(self) -> frozenset[str]: ...   # names_of_things と {actor}。相手がいれば {target} も
    def placement(self, location: DesignLocation) -> RulePlacement: ...
    # 相手がいれば RulePlacement.in_person_interaction、いなければ in_action。相手のいない行為の知らせの相手で Target を選べば DesignFlaw
    # 読み込みは has_target と target_is_down で、相手の文 (target) を読むか、どの形で読むかを決める

@final
@dataclass(frozen=True)
class SurroundingsTexts:                    # 行為ではなく、本人に直接届く場面と知らせの文。シナリオが世界全体で 1 つ書く (#2174)
    people_here: TextWithUnassignedPeople   # 「ここには{people}がいる。」。{people} をちょうど 1 回だけ書き、ほかの穴は書けない
    bodies_here: TextWithUnassignedPeople   # 「{people}が倒れている。」。倒れている人と死んだ人。穴の決まりは people_here と同じ
    joiner: str                             # {people} に 2 人以上入るとき、人の穴どうしをつなぐ言葉 (共通の部品では「、」)。1 人のときは使わない。空でない 1 行
    waking: TextWithUnassignedPeople        # 「目が覚めた。」。介抱されて起きた本人へ。穴は書けない
    darkening: TextWithUnassignedPeople     # 「辺りが暗くなった。」。明るさが下がった場所の人へ。穴は書けない

    def scene_as_seen(self, *, people: tuple[PersonRef | Unidentified, ...], bodies: tuple[PersonRef | Unidentified, ...]) -> TextWithAssignedPeople: ...
    # {people} を 1 人ずつの穴 ({person_1}、{person_2} ...) に広げ、渡した順に joiner でつなぐ。穴の番号は people_here から bodies_here へ通しで付ける
    # いる側の文だけを people_here、bodies_here の順につなぐ。どちらも 1 人も渡さなければ断る (誰もいなければ文を出さない)
    # 受け取るのは場面 (VisibleSurroundings) の見え方を当てた後の人。誰を見分けられるかは場面の見え方の規則だけが決める (#2154)
    # 1 つの穴に入るのは 1 人で、名前は見る人の側で埋まる (perception.md)。item_joiner は呼び名の文字をつなぐが、joiner はまだ名前の決まっていない穴どうしをつなぐ
    # 行為の知覚の表 (BuiltInActionPerceptions) に入れないのは、どの行も見る人と音を持つ「ある人の行為の見え方」で、場面と知らせはそのどちらも持たないため
    # 明るさが上がったときの文は持たない。上がったときは場面を届け直す (perception.md)

@final
@dataclass(frozen=True)
class ShopTexts:                            # 店の呼び名と、店で起きたことの知らせの文。シナリオが世界全体で 1 つ書く (D2224)
    person_shop_label: TextWithUnassignedPeople   # 「{owner}の店」。{owner} は持ち主で、見る人ごとの呼び方で埋まる
    scenario_shop_label: str                      # 「{keeper}の店」。{keeper} は作者の店の keeper_name で埋める
    closed_mark: str                              # 閉じた店に添える文 (「閉まっている」)
    sold_notice: str                              # 留守でも持ち主に届く知らせ。「店で{item}が{count}つ売れ、{gold}が入った。」
    bought_notice: str                            # 「店が{item}を{count}つ買い取り、{gold}を払った。」
    # 知らせの文には人のプレースホルダーを書けない。誰が買ったかは持ち主に伝えない
    # {item} は品物の名前、{count} は数、{gold} は gold_label で埋める。ほかの穴は書けない

@final
@dataclass(frozen=True)
class RefusalTexts:                         # 作者の条件に付かない、断られた理由の文。シナリオが世界全体で 1 つ書く
    common_rules: Mapping[CommonRuleRefusalKind, TextWithUnassignedPeople]   # Busy、TooTired、NotTogether、OutOfReach など ([action.md](action.md))
    world_state: Mapping[RefusalCode, TextWithUnassignedPeople]              # 集約が断ったとき (籠が満員、荷が空)。error_code ごと
    hidden: TextWithUnassignedPeople                                         # 行う人が知りえない所属を見て断ったとき。理由を言わない文
    unlisted: TextWithUnassignedPeople                                       # world_state の表に無い RefusalCode で断ったとき (#2146)

@final
@dataclass(frozen=True)
class WorldIntroduction:                    # 全員に同じ、世界の導入。ステージ 8 で案内 (being.contract の Orientation) に渡す。人ごとの目的は持たない (D2222)
    text: DescriptionText
    premises: DescriptionText               # 世界の前提の箇条 (「昇降機は一度しか動かない」)。目的ではない

@final
@dataclass(frozen=True)
class Route:
    start: SpotId                               # 両方向に通れる通路は、passages だけではどちらの端から出るかが決まらない
    passages: tuple[PassageDeclaration, ...]    # 1 本以上。start から順にたどれる (片道は ends の前の端から)

    @property
    def destination(self) -> SpotId: ...
    def end_of_passage(self, passage_index: int) -> SpotId: ...

NoRoute()                                       # 通れる通路をたどって目的地に着けない。出発地と目的地が同じときも

@final
@dataclass(frozen=True)
class StartingPerson:                           # 登場人物の始まり。名前ではなく宣言で持つ
    person: PersonId
    spawn_spot: SpotDeclaration
    items: tuple[ItemSpecDeclaration, ...]
    held: tuple[ItemSpecDeclaration, ...]
    groups: tuple[GroupDeclaration, ...]
    knows: tuple[PersonId, ...]
    hp: HitPoints                               # 登場人物の値か、無ければ WorldRules の既定
    pack_capacity: Capacity
    gold: Gold                                  # CharacterDeclaration.initial_gold

@final
@dataclass(frozen=True)
class InitialWorld:                             # 宣言どうしを組み合わせないと作れない始まりの世界だけ。物の状態などは集約が宣言から作る
    people: tuple[StartingPerson, ...]
    raised_flags: frozenset[FlagDeclaration]    # initially_raised の旗
    stage: WorldStageDeclaration | NoWorldStages
    weather: WeatherState | NoWeather           # WeatherDeclaration.initial


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
        object_looks: Iterable[ObjectLooksDeclaration],
        monster_presences: Iterable[MonsterPresenceDeclaration],          # monster.md
        monster_perceptions_by_spec: Iterable[MonsterPerceptionsDeclaration],
        group_decision_rules: Iterable[GroupDecisionRulesDeclaration],
        happenings: Iterable[HappeningDeclaration],
        reactions: Iterable[ReactionDeclaration],
        discoverables: Iterable[DiscoverableDeclaration],
        joint_actions: Iterable[JointActionDeclaration],
        person_interactions: Iterable[InteractionDeclaration],
        ending: EndingDeclaration,
        world_rules: WorldRules,
        refusal_texts: RefusalTexts,
        built_in_action_perceptions: BuiltInActionPerceptions,
        surroundings_texts: SurroundingsTexts,              # 場面と知らせの文 (#2174)
        shop_texts: ShopTexts,                              # 店の呼び名と知らせの文 (D2224)
        monster_perceptions: MonsterPerceptions,            # 種類ごとに書き換えなかったときの既定
        monster_health: MonsterHealthTexts,                 # 傷の具合の境と文
        monster_doing: MonsterDoingTexts,                   # 状態ごとの、いましていることの文
        weather: WeatherDeclaration | NoWeather,
        day_night: DayNightDeclaration | NoDayNight,
        initial_stage: WorldStageDeclaration | NoWorldStages,
        introduction: WorldIntroduction,
    ) -> "WorldDesign": ...

    @property
    def nouns(self) -> DeclaredNouns: ...
    @property
    def world_rules(self) -> WorldRules: ...
    @property
    def ending(self) -> EndingDeclaration: ...
    @property
    def introduction(self) -> WorldIntroduction: ...
    @property
    def refusal_texts(self) -> RefusalTexts: ...
    @property
    def built_in_action_perceptions(self) -> BuiltInActionPerceptions: ...
    @property
    def surroundings_texts(self) -> SurroundingsTexts: ...
    @property
    def shop_texts(self) -> ShopTexts: ...
    @property
    def weather(self) -> WeatherDeclaration | NoWeather: ...
    @property
    def day_night(self) -> DayNightDeclaration | NoDayNight: ...

    def interaction_on_object(self, obj: ObjectId, interaction: InteractionId) -> InteractionDeclaration: ...   # 宣言が無ければ UndeclaredVerbException。人への操作も同じ
    def interaction_on_item(self, item_spec: ItemSpecId, interaction: InteractionId) -> InteractionDeclaration: ...
    def interactions_on_object(self, obj: ObjectId) -> tuple[InteractionDeclaration, ...]: ...
    def interactions_on_item(self, item_spec: ItemSpecId) -> tuple[InteractionDeclaration, ...]: ...
    def use_of_item(self, item_spec: ItemSpecId) -> ItemUseDeclaration | NotUsable: ...
    def section_access(self, section: SpotSectionId) -> SectionAccessDeclaration: ...
    def passage_traversal(self, passage: PassageId) -> Condition: ...                   # 宣言が無ければ、いつでも真の条件
    def world_stage_effects(self, stage: WorldStageId) -> WorldStageEffectsDeclaration: ...   # 宣言が無ければ、出入りで何もしない (NoEffect) 宣言
    def looks_of(self, obj: ObjectId) -> ObjectLooksDeclaration: ...
    def presence_of(self, spawn: MonsterSpawnId) -> MonsterPresenceDeclaration: ...      # 宣言が無ければ AlwaysPresent
    def monster_perceptions_of(self, spec: MonsterSpecId) -> MonsterPerceptions: ...    # 宣言が無ければ世界の既定                     # 宣言が無ければ、見え方が空の宣言
    def group_decision_rules(self, decision: GroupDecisionId) -> GroupDecisionRulesDeclaration: ...
    def person_interaction(self, interaction: InteractionId) -> InteractionDeclaration: ...   # 殴る、盗むなど、人への操作
    def happenings(self) -> tuple[HappeningDeclaration, ...]: ...
    def joint_actions(self) -> tuple[JointActionDeclaration, ...]: ...
    def reactions(self) -> tuple[ReactionDeclaration, ...]: ...
    def discoverables_at(self, spot: SpotId) -> tuple[DiscoverableDeclaration, ...]: ...
    def route(self, start: SpotId, destination: SpotId, passable: frozenset[PassageId]) -> Route | NoRoute: ...
        # passable の通路だけを、宣言の向き (two_way と ends の順) にたどる。呼ぶ側が PassageStates の今の状態から渡す
        # かかる tick の合計が最も小さい道、同じなら通路の数が少ない道、それも同じなら宣言の並びが先の通路を通る道
    def initial_world(self) -> InitialWorld: ...
    def warnings(self) -> tuple[DesignWarning, ...]: ...


@final
@dataclass(frozen=True)
class DesignLocation:                       # 宣言の種類・名前・欄 (use_cases.md)
    declaration: str
    name: str
    field: str
    file: ScenarioFile | NoScenarioFile = NoScenarioFile()   # どのファイルに書いたか。ドメインは知らないので既定のまま作り、読み込む側が in_file で付ける (#2057)

    def in_file(self, file: ScenarioFile | NoScenarioFile) -> "DesignLocation": ...
    # 文にすると「common/ja_default.yaml: world 'world' rules.fatigue.limit」。ファイルが無ければ名前より前を書かない

ScenarioFile(name: str)                     # シナリオや共通の部品のファイルの名前 (シナリオのあるフォルダからの道筋)
NoScenarioFile()

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
infrastructure: YAML を読む (scenario_format.md)
  ① 名詞の宣言を作る → DeclaredNouns
  ② 動詞の宣言 (名詞に付く動詞、条件、効果、操作、出来事) を、DeclaredNouns から名詞を引いて作る
  ③ WorldDesign.compose
```

- 名詞の宣言は互いを宣言ではなく ID で指す (`SpotSectionDeclaration.reachable_objects`、`CharacterDeclaration.spawn_spot` など)。ID が宣言にあるかは `DeclaredNouns` が作るときに確かめ、無ければ `DesignFlaw` にする。`GroupDeclaration.grouping` だけは、分け方が集団を指さず循環しないので、宣言のまま持つ
- `DeclaredNouns` は ID の有無のほかに、次も照らし合わせて `DesignFlaw` にする (#1995)。集まりの持つ分け方が `groupings` に無いか、同じ `grouping_id` の宣言と中身が違う (`groups_in` が返せなくなる)。区画の `reachable_objects` の物が区画と違う場所にある。登場人物の `initial_groups` に同じ分け方の集まりが 2 つある (`group_of` は 1 つしか返せない)
- 宣言 1 つだけで判断できる誤り (通路の状態名の重複、両端が同じ場所の通路、`initial_state` が `states` に無い、区画の `reachable_objects` の重複、状態の鍵の重複、種類に合わない `initial`、状態の鍵の種類に合わない効果と条件 (旗の鍵に数を足す、など。#2062)) は、宣言の型が作るときにドメイン例外で断る。ほかの宣言と照らし合わせて分かる誤りは `DeclaredNouns` が確かめる。どちらで止めても作者に返るのは `DesignFlaw` で、宣言の型の例外は読み込む側が場所を付けて `DesignFlaw` に包む
- `Unchanged` (雰囲気を変える効果で、変えない欄) と `NoCapacity` (区画の定員が無い) は、中身の無い型

- 誤りは最初の 1 つで止めず、集めてから 1 つの `WorldDesignFlawsException` で投げる。どの誤りにも場所 (`DesignLocation`) を付ける。YAML の書き方の誤り (必須キーの欠け、列挙の綴り違い、鍵の重複) も infrastructure が `DesignFlaw` に包み、素の `KeyError` / `ValueError` を外に出さない
- compose は、条件と効果を置いた場所ごとに使える主語 ([condition.md](condition.md)) と、`requirements()` を照らし合わせる
- `initially_raised` でもなく、どの `RaiseFlagEffect` にも出てこない旗を条件が見ていたら `DesignFlaw`。立てるだけで誰も見ない旗は `DesignWarning`
- 締める出来事 (`CloseGroupDecisionEffect`) が 1 つも無い集団の決定は `DesignWarning`。猶予 (`DeathRule.grace`) が 0 なのに介抱がある世界は `DesignFlaw`
- 作者が書かなかった知覚の文 (目撃の文、された人の文、音の文、起きてから気づく文) は、読み込む側が既定の文の表 (データ) から埋め、`DesignWarning` を残す。倒れていた本人が起きてから気づく文だけは、書かなければ気づかない (`NotNoticedLater`)。介抱の相手の文 (`NoticedOnWaking`) も同じで、書かなければ `NoTarget` になり、警告もしない (#2076)
- 断りの文の表 (`RefusalTexts`)、組み込みの行為の知覚の文 (`BuiltInActionPerceptions`)、場面と知らせの文 (`SurroundingsTexts`) の既定は、コードではなくデータ (共通のシナリオの部品) として 1 つ用意し、シナリオはそれを取り込んで必要な行だけ書き換える。起きうる理由や、世界で行える組み込みの行為が表に無ければ `DesignFlaw`
- 理由が誰かに届く条件 (操作の前提、区画に入る条件、通路を通る条件) の根に `failure_text` が無ければ `DesignFlaw`。出来事・反応・終わり・見つかる物の条件には求めない
- 効果と条件が読む引数の名前が、操作の宣言の `arguments` に無ければ `DesignFlaw`
- `WorldStage`・昼夜・天候を宣言していない世界で、それを見る条件を書いていれば `DesignFlaw`。昼夜に宣言していない段階の名前を見る条件も同じ
- 行う人に知りえない所属 ([condition.md](condition.md) の伏せた所属) を見る前提は `DesignWarning`。前提は、操作の前提、区画の入る条件、通路の通り方の条件
- 条件が読む出来事の ID (`HappeningHasFiredCondition` などは宣言ではなく `HappeningId` を持つ。自分を読む出来事を作れるようにするため) が宣言に無ければ `DesignFlaw` (#2057)
- 出来事・反応・見つかる物・二人で合わせる操作の ID が重なれば `DesignFlaw`。`ScenarioProgress` などが ID で記録するので、重なると 2 つが混ざる
- 区画ごとの出入り (`SectionAccessDeclaration`) と、集団の決定ごとの決まり (`GroupDecisionRulesDeclaration`) が 1 つずつ無ければ `DesignFlaw`。二人で合わせる操作が求める物体の操作が宣言に無ければ `DesignFlaw`
- 組み込みの行為の知覚の文は、世界で行える組み込みの行為 (介抱は `TendRule` があるときだけ) をすべて持たなければ `DesignFlaw`。知らせの相手の選び方は、行為の中に置いた条件として、ほかの宣言と同じく照らし合わせる。`Actor` はどの行でも、`Target` は相手のいる行 (`BuiltInPerceptionRow.has_target`) でだけ使える (#2076)。断りの文の表の `world_state` は、起きうる `RefusalCode` をドメインで列挙できないので compose では確かめない
- compose が照らし合わせに使う材料 (主語、読む引数、段階・昼夜・天候を読むか、立てる旗、締める決定、伏せられうる所属、読む出来事) は、条件と効果の `requirements()` が答える。根に文があるかは `Condition.explains_failure()` が答える
- 作者の店 (`ScenarioShopDeclaration`) の品目が、宣言に無い品物の種類を指せば `DesignFlaw`。作者の店の置き場所が宣言に無い場所なら `DesignFlaw`。店の行為の知覚の文は、店を出せる場所か作者の店がある世界でだけ求める (D2224)
- 物の見え方の宣言 (`ObjectLooksDeclaration`) は物ごとに 1 つまで。宣言に無い物を指せば `DesignFlaw`。見え方 (`ObjectLook.when`) の条件は、世界の状態だけで決まるものに限る。`requirements()` が、きっかけから人を引く主語 (名指しした人 `NAMED_PERSON` は除く)・`uses_chance`・`uses_action_arguments` のどれかを持てば `DesignFlaw`。人によって変わる見え方や、見渡すたびに変わる見え方になるため。名指しした人の状態は見る人で変わらないので使える (#2067、#2070)
- 宣言に無い通路の状態の名前、呼び名 (`display_name`) の無い値が文に出るときは、`DesignFlaw` で止める
