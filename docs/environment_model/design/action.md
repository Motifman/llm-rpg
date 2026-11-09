# 行為 (ActionAttempt)

```python
class ActionAttempt(Protocol):
    @property
    def actor(self) -> PersonId: ...
    def kind(self) -> ActionKind: ...
    def actor_requirement(self) -> ActorRequirement: ...
    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]: ...
    def exertion(self) -> Exertion: ...
    def person_as(self, kind: SubjectKind) -> PersonId: ...   # 答えられない主語は SubjectNotInTriggerException
    def this_item(self) -> ItemInstanceId: ...                # 品物の無い行為は ItemNotInTriggerException
    def acting_person(self) -> PersonId | NoActingPerson: ...    # 行う人。行為は actor、行為でないきっかけは NoActingPerson
    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId: ...   # 引数の無い行為と、行為でないきっかけは ArgumentNotInTriggerException
    def fall_cause_for(self, victim: PersonId) -> FallCause: ...   # acting_person() が答える人で、傷ついたのがその人以外なら StruckByPerson、それ以外は WorldHappening()。action/ の共通の関数を呼ぶ
    def can_start_while_busy(self) -> bool: ...               # 前の行為を行っているあいだに始められるか。話すことだけが真
    def is_allowed_in(self, stage: WorldStageDeclaration | NoWorldStages) -> bool: ...   # 組み込みの行為は stage.allows(ActionKind)、作者の操作は stage.allows_interaction(InteractionId) に尋ねる。NoWorldStages はどの行為も許す
    def done_as(self) -> frozenset[ActionKind | InteractionId]: ...   # 最後に行った行為として記録する鍵。組み込みの行為は {kind}、作者の操作は {kind, interaction_id}


Trigger = ActionAttempt | HappeningFired | ReactionFired | GroupDecisionResult | JointActionCompleted | WorldTimePassing | LookingAround | EachPersonOf
# どのきっかけも person_as、this_item、acting_person、argument、fall_cause_for を持つ。GroupDecisionResult は CHOSEN_BY_GROUP だけを答え、ほかの行為でないきっかけは何も答えない
# 行為でないきっかけの acting_person は NoActingPerson、fall_cause_for は WorldHappening()。EachPersonOf は person_as(EACH_PERSON) のほかは外のきっかけに任せる

@final
@dataclass(frozen=True)
class EachPersonOf:                         # ForEveryone などの中で、外のきっかけと「その人」を包む
    outer: Trigger
    person: PersonId                        # EACH_PERSON にはこの人を、ほかの主語と品物は outer が答える

@final
@dataclass(frozen=True)
class JointActionCompleted:
    joint: CompletedJointAction             # joint_id を答える Protocol。JointActionDeclaration が満たす

@final
@dataclass(frozen=True)
class HappeningFired:
    happening: FiredHappening               # happening_id を答える Protocol。HappeningDeclaration が満たす

@final
@dataclass(frozen=True)
class ReactionFired:
    reaction: FiredReaction                 # reaction_id を答える Protocol。ReactionDeclaration が満たす

@final
@dataclass(frozen=True)
class GroupDecisionResult:
    decision: GroupDecisionDeclaration
    chosen: PersonId

@final
@dataclass(frozen=True)
class WorldTimePassing:                     # 時間が進んだことがきっかけ (PassWorldTime の中の空腹、死の猶予など)
    tick: WorldTick

@final
@dataclass(frozen=True)
class LookingAround:                        # 物の見え方 (ObjectLook) を確かめるきっかけ。何も答えない
    tick: WorldTick

ActorRequirement = LivingOnly | LivingOrDeparted
CopresenceRequirement = WithPerson | WithObject | WithGroundItem | WithMonster   # 商人と市場 (取引の Issue) は、設計するときに足す
Exertion = UsesBody | DoesNotUseBody

class ActionKind(Enum):                     # どの世界にもある行為の種類。作者の操作は InteractionId で指す
    TRAVEL = "TRAVEL"
    SPEAK = "SPEAK"
    LISTEN = "LISTEN"
    WAIT = "WAIT"
    TEND = "TEND"
    HAND_OVER = "HAND_OVER"
    PICK_UP = "PICK_UP"
    DROP = "DROP"
    SEARCH = "SEARCH"
    USE_ITEM = "USE_ITEM"
    ENTER_SECTION = "ENTER_SECTION"
    LEAVE_SECTION = "LEAVE_SECTION"
    HOLD = "HOLD"
    PUT_AWAY = "PUT_AWAY"
    CAST_BALLOT = "CAST_BALLOT"
    INTERACT_WITH_OBJECT = "INTERACT_WITH_OBJECT"
    INTERACT_WITH_CARRIED_ITEM = "INTERACT_WITH_CARRIED_ITEM"
    INTERACT_WITH_PERSON = "INTERACT_WITH_PERSON"
    ATTACK_MONSTER = "ATTACK_MONSTER"
    # 取引と市場の種類は、その宣言を設計するときに足す
Manner = Openly | Stealthily
# Stealthily: 拾う・置く・渡すと、allows_stealth の操作だけ。見ていた人ごとに StealthRule の確率で気づく
# (気づいた人にはふつうの文、気づかなかった人には何も届かない)。行っているあいだは StealthRule.duration_multiplier 倍、物音は 1 段小さい
```

### 行為ごとの性質

共通の前提は、行為の種類を見分けずに、行為の型自身に性質を尋ねる (`kind() is SPEAK` のように外から分けない)。作者の操作は操作の宣言 (`InteractionDeclaration`) の欄を答える。組み込みの行為は次の値を答える。

| 行為 | 体を使う (`exertion`) | 最中でも始められる | 近くにいる必要 (`copresence_requirements`) | 去った人も (`actor_requirement`) | こっそり |
|---|---|---|---|---|---|
| 移動 (TRAVEL) | ○ | × | — | ○ | × |
| 話す (SPEAK) | × | ○ | ささやきだけ相手 | × | × |
| 耳を澄ます (LISTEN) | × | × | — | ○ | × |
| 待つ (WAIT) | × | × | — | ○ | × |
| 介抱 (TEND) | ○ | × | 相手 | × | × |
| 渡す (HAND_OVER) | ○ | × | 相手 | × | ○ |
| 拾う (PICK_UP) | ○ | × | 地面の品物 | × | ○ |
| 置く (DROP) | ○ | × | — | × | ○ |
| 探す (SEARCH) | ○ | × | — | × | × |
| 品物を使う (USE_ITEM) | ○ | × | — | × | × |
| 区画に入る・出る | 区画の出入りの宣言 | × | — | × | × |
| 持ち替え (HOLD / PUT_AWAY) | × | × | — | × | × |
| 投票 (CAST_BALLOT) | × | × | — | × | × |
| 物・品物・人への操作 | 操作の宣言 | × | 物 / — / 相手 | 操作の宣言 | 操作の宣言 |

- 去った人にできるのは、移動・耳を澄ます・待つだけ (幽霊は観戦者に近い)
- 持ち替えは、疲れ切っていても持ち替えられるよう体を使わない扱い
- 形の誤り (こっそり行えない行為に `Stealthily`、`reaches_unseen` でない操作に `SomeoneInTheDark`) は、行為を作るときにドメイン例外で断る。ツールの呼び方の誤りとして返す
- `SomeoneInTheDark` の相手は、行うときに世界がその場から選ぶ。暗さは知覚 (ステージ 5) の明るさで決まるので、共通の前提では確かめない。選べる人がいなければ、行為を行うユースケース (ステージ 7) が `NoOneFoundInTheDark` として断る

## 行為の型

```python
ObjectInteractionAttempt(actor: PersonId, obj: ObjectDeclaration, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
CarriedItemInteractionAttempt(actor: PersonId, item: ItemInstanceId, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
PersonInteractionAttempt(actor: PersonId, target: PersonId | SomeoneInTheDark, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)

ItemUseAttempt(actor: PersonId, item: ItemInstanceId)
TendAttempt(actor: PersonId, target: PersonId)
ItemHandOverAttempt(actor: PersonId, deliveries: tuple[Delivery, ...], manner: Manner)     # 1 件以上
GroundItemPickupAttempt(actor: PersonId, item: ItemInstanceId, manner: Manner)
ItemDropAttempt(actor: PersonId, item: ItemInstanceId, manner: Manner)
SpotSearchAttempt(actor: PersonId)
EnterSectionAttempt(actor: PersonId, access: DeclaredSectionAccess)   # 区画の出入りの宣言の欄 (section、exertion) を読む Protocol
HoldItemAttempt(actor: PersonId, item: ItemInstanceId)        # 手がふさがっていれば、今持っている物を荷にしまう
PutAwayItemAttempt(actor: PersonId, item: ItemInstanceId)
LeaveSectionAttempt(actor: PersonId, access: DeclaredSectionAccess)   # 外側が、本人のいる区画の出入りの宣言を渡す

TravelAttempt(actor: PersonId, destination: SpotDeclaration)
SpeechAttempt(actor: PersonId, reach: Whisper | OrdinaryVoice | Shout, content: SpeechContent)
ListeningAttempt(actor: PersonId)
WaitAttempt(actor: PersonId, reason: WaitReason | NoReason)
GroupDecisionBallotAttempt(actor: PersonId, decision: GroupDecisionDeclaration, choice: VoteFor | Abstain)

Whisper(to: PersonId) | OrdinaryVoice() | Shout()
SpeechContent(text: str)                # 空でない文
WaitReason(text: str) | NoReason()      # 空でない文か、理由なし
Delivery(item: ItemInstanceId, to: PersonId)   # 1 回で複数の相手に渡せる
SomeoneInTheDark()      # 暗がりの見分けのつかない人。相手は世界がその場から選ぶ (1 人なら決まる)。真っ暗では人がいることも分からないので使えない
VoteFor(person: PersonId) | Abstain()   # world_progress の GroupDecision のものを使う

ActionArguments = Mapping[ArgumentName, TextArgumentValue | ItemInstanceId]
TextArgumentValue(text: str)            # 空でない文
# 操作の宣言の arguments (world_design.md) に従って外側が作る。品物はエージェントが呼び方で指し、外側が場面に見えている品物から ItemInstanceId を引いて入れる
# ArgumentName は value_object/ の 1 つを、条件・効果・行為が使う
```

物・品物・人への操作は、操作の宣言 (`InteractionDeclaration`) の欄 (`interaction_id`、`exertion`、`actor_requirement`、`allows_stealth`、`reaches_unseen`、`arguments`) を読んで性質を答える。

モンスターへの攻撃は `AttackMonsterAttempt(actor, monster: MonsterId)` ([monster.md](monster.md))。商人・取引・市場の行為 (取引の Issue) は、設計するときに足す。

## 断られたとき

```python
@final
@dataclass(frozen=True)
class ActionRefusal:
    attempt: ActionAttempt
    reason: CommonRuleRefusal | PreconditionRefusal | WorldStateRefusal
    text: TextAboutPeople                   # 見る人ごとの呼び方への置き換えは、行った人に届けるところで行う

CommonRuleRefusal = ActorCannotAct | Busy | NotTogether | OutOfReach | TooTired | NotAllowedInThisStage | NoOneFoundInTheDark
# Busy: 前の行為を行っているあいだ (話すことだけはできる)
# ActorCannotAct: 倒れている、結末が決まった、去った人に許されない行為 (ActorRequirement)
# OutOfReach: 区画の中からしか届かない物に、外から触ろうとした

@final
@dataclass(frozen=True)
class PreconditionRefusal:
    failure: FailureReason | HiddenFailure

@final
@dataclass(frozen=True)
class WorldStateRefusal:                    # 世界を変える途中で集約が断った (満員、相手がその品を持っていない)
    code: RefusalCode                       # 集約が投げたドメイン例外の error_code を包む型
```

断られた理由の文は、ドメインに決まった文を持たない。

- `PreconditionRefusal(FailureReason)`: 作者の `failure_text` ([condition.md](condition.md))
- 共通の決まり (`CommonRuleRefusal`)、集約の断り (`WorldStateRefusal` の `RefusalCode`)、伏せた理由 (`PreconditionRefusal(HiddenFailure)`): シナリオの断りの文の表 (`RefusalTexts`、[world_design.md](world_design.md))

## 共通の前提

```python
class ActionPrerequisiteCheck:
    def refusal(self, attempt: ActionAttempt, facts: WorldFacts, refusal_texts: RefusalTexts) -> ActionRefusal | None: ...
        # 段階は facts.world_stage()、規則は facts.rules()、行っているあいだは facts.vitals(actor).is_busy(now)、
        # 区画の中から届くかは facts.whereabouts().can_reach(...) に尋ねる
```

## できること

```python
@final
@dataclass(frozen=True)
class AvailableAction:
    attempt: ActionAttempt
    standing: Doable | NotNow

@final
@dataclass(frozen=True)
class NotNow:
    reason: TextAboutPeople

@final
@dataclass(frozen=True)
class AvailableActions:
    actions: tuple[AvailableAction, ...]
```

- 実際に試したときと同じ確認 (`ActionPrerequisiteCheck.refusal` と行為ごとの前提の `failure_reason`) で作る。`HiddenFailure` になった行為は「できる」と出す (一覧に出る / 出ないの差から伏せた所属が漏れないため。[condition.md](condition.md))。いまできない行為を消さずに理由つきで出すのは design_decisions #37 のとおり (消すと、エージェントが無い操作名を作って呼ぶ)
- 行為を始めた瞬間に効果が起き、そのあと `WorldRules.action_durations` (または `InteractionDeclaration.duration`) のあいだ `PersonVitals.is_busy` が真になる。そのあいだ、話す以外の行為は `Busy` で断る
- 一覧は前提を確かめるだけで作る。考えているあいだに世界が変わるので目安で、届いたときに必ず確かめ直す。集約が断るもの (満員など) は届いたときに断る
- 行為の対象の候補は、場面 (`VisibleSurroundings`) に出ているものに限る。「誰か」(`Unidentified`) には `SomeoneInTheDark` で行う。ターンごとに振り直す呼び方 (「人影1」) は、記憶に残った呼び方が次のターンで別のものを指すので使わない (design_decisions #3)
