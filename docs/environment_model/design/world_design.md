# 設計図 (WorldDesign)

シナリオが宣言したもの。run の間は変わらない。

```python
# 名詞の宣言

@final
@dataclass(frozen=True)
class FlagDeclaration:
    flag_id: FlagId
    meaning: str

@final
@dataclass(frozen=True)
class SpotDeclaration:
    spot_id: SpotId
    name: str
    description: str
    atmosphere: SpotAtmosphere

@final
@dataclass(frozen=True)
class PassageDeclaration:
    passage_id: PassageId
    ends: tuple[SpotId, SpotId]
    two_way: bool
    travel_ticks: int
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
class ItemSpecDeclaration:
    item_spec_id: ItemSpecId
    name: str
    description: str
    on_use: Effect | NotUsable
    interactions: tuple[InteractionDeclaration, ...]
    state_keys: tuple[ItemStateKeyDeclaration, ...]
    lights_up: bool

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
    initial_groups: tuple[GroupId, ...]
    knows_at_start: tuple[PersonId, ...]

@final
@dataclass(frozen=True)
class WorldStageDeclaration:
    stage_id: WorldStageId
    name: str
    description: str
    allowed_actions: frozenset[ActionKind] | AllActionsAllowed
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
    when_decided: Effect
    when_undecided: Effect

@final
@dataclass(frozen=True)
class DiscoverableDeclaration:
    discoverable_id: DiscoverableId
    spot_id: SpotId
    found_text: str
    condition: Condition
    when_found: Effect
    finding: Finding                         # ONCE_IN_WORLD / ONCE_PER_PERSON


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


# 動詞の宣言

@final
@dataclass(frozen=True)
class InteractionDeclaration:
    interaction_id: InteractionId
    display_label: str
    precondition: Condition
    effect: Effect
    success_text: TextWithPeople            # 行った本人の体の刺激になる
    shows_on_success: tuple[ShownToActor, ...]
    exertion: Exertion
    actor_requirement: ActorRequirement
    perceived_as: PerceptionDeclaration

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
    texts: SightTexts
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
    text: TextWithPeople
    salience: Salience

@final
@dataclass(frozen=True)
class PerceptionDeclaration:                # 行為が周りにどう知覚されるか
    witness: SightTexts
    target: SightTexts | NoTarget
    sound: SoundDeclaration | Silent
    salience: Salience

@final
@dataclass(frozen=True)
class SoundDeclaration:
    loudness: Loudness                      # 書かなければ、開け閉めは大きい、壊すはとても大きい、ほかはふつう
    clear: TextWithPeople
    muffled: TextWithPeople

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
class ChangesEvery:
    ticks: int
    transitions: WeatherTransitions        # 書かなければ既定の表

@final
@dataclass(frozen=True)
class WorldRules:
    tend: TendRule
    attack: AttackRule
    fatigue: FatigueRule
    death: DeathRule
    departed_persons_act: bool
    hearing: HearingValues
    idle_limit: IdleLimit                   # 何も起きないまま、この間が過ぎたら手番を起こす

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
        ending: EndingDeclaration,
        world_rules: WorldRules,
        initial_stage: WorldStageId | NoWorldStages,
        initial_flags: Iterable[FlagDeclaration],
    ) -> "WorldDesign": ...

    @property
    def nouns(self) -> DeclaredNouns: ...
    @property
    def world_rules(self) -> WorldRules: ...
    @property
    def ending(self) -> EndingDeclaration: ...

    def interaction_on_object(self, obj: ObjectId, interaction: InteractionId) -> InteractionDeclaration: ...
    def interaction_on_item(self, item_spec: ItemSpecId, interaction: InteractionId) -> InteractionDeclaration: ...
    def happenings(self) -> tuple[HappeningDeclaration, ...]: ...
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

- 作者が書かなかった知覚の文 (目撃の文、された人の文、音の文、起きてから気づく文) は、compose が決まった文で埋め、`DesignWarning` を残す。倒れていた本人が起きてから気づく文だけは、書かなければ気づかない (`NotNoticedLater`)
- 宣言に無い通路の状態の名前、呼び名 (`display_name`) の無い値が文に出るときは、`DesignFlaw` で止める
