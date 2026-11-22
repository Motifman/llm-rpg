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
    def operates(self, obj: ObjectId, interaction: InteractionId) -> bool: ...   # その物体のその操作か。物体の操作だけが真を返す。二人で合わせる操作の帳簿が部分を決めるのに使う (D2173)


Trigger = ActionAttempt | HappeningFired | ReactionFired | GroupDecisionResult | GroupDecisionUnresolved | WorldStageChanged | JointActionCompleted | JointActionTimedOut | WorldTimePassing | LookingAround | WorldConditionsSettling | EachPersonOf
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
    joint: SettledJointAction               # joint_id を答える Protocol。JointActionDeclaration が満たす

@final
@dataclass(frozen=True)
class JointActionTimedOut:                  # 時間切れの効果のきっかけ。揃っていないので JointActionCompleted を流用しない
    joint: SettledJointAction

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
class GroupDecisionUnresolved:              # 集団の決定が決まらなかったこと (when_undecided)。選ばれた人がいないので何も答えない
    decision: GroupDecisionDeclaration

@final
@dataclass(frozen=True)
class WorldStageChanged:                    # 段階が変わったこと。出る段階の when_left と入る段階の when_entered に同じものを渡す。何も答えない
    before: WorldStageId
    after: WorldStageId
    at: WorldTick

@final
@dataclass(frozen=True)
class WorldTimePassing:                     # 時間が進んだことがきっかけ (PassWorldTime の中の空腹、死の猶予など)
    tick: WorldTick

@final
@dataclass(frozen=True)
class LookingAround:                        # 物の見え方 (ObjectLook) を確かめるきっかけ。何も答えない
    tick: WorldTick

@final
@dataclass(frozen=True)
class WorldConditionsSettling:              # 終わりの条件を確かめるきっかけ (SettleWorldConditions)。何も答えない
    tick: WorldTick                         # コマンドの後の判定を「時間が進んだから終わった」と読ませないよう、WorldTimePassing と分ける

ActorRequirement = LivingOnly | LivingOrDeparted
CopresenceRequirement = WithPerson | WithObject | WithGroundItem | WithMonster | WithShop
# WithShop(shop: ShopId): 行う人が店と同じ場所にいる。区画の中からでも届く (店は区画に置かない) (D2224)
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
    OPEN_SHOP = "OPEN_SHOP"                 # 店の行為 (D2224)。下の「店の行為」
    CLOSE_SHOP = "CLOSE_SHOP"
    EDIT_SHOP_LINE = "EDIT_SHOP_LINE"
    REWRITE_SHOP_LOOK = "REWRITE_SHOP_LOOK"
    BUY_FROM_SHOP = "BUY_FROM_SHOP"
    SELL_TO_SHOP = "SELL_TO_SHOP"
    COLLECT_FROM_SHOP = "COLLECT_FROM_SHOP"
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
| 品物を使う (USE_ITEM) | ○ | × | 持っている品物 | × | × |
| 区画に入る・出る | 区画の出入りの宣言 | × | — | × | × |
| 持ち替え (HOLD / PUT_AWAY) | × | × | — | × | × |
| 投票 (CAST_BALLOT) | × | × | — | × | × |
| 店を開く (OPEN_SHOP) | ○ | × | — (いまいる場所に開く) | × | × |
| 店を閉じる・品目を編集する・見た目を書き直す・受け取った品を引き取る | ○ | × | 自分の店 | × | × |
| 店で買う・店に売る (BUY_FROM_SHOP / SELL_TO_SHOP) | ○ | × | 相手の店 | × | × |
| 物・品物・人への操作 | 操作の宣言 | × | 物 / 持っている品物 / 相手 | 操作の宣言 | 操作の宣言 |

- 去った人にできるのは、移動・耳を澄ます・待つだけ (幽霊は観戦者に近い)
- 持ち替えは、疲れ切っていても持ち替えられるよう体を使わない扱い
- 形の誤り (こっそり行えない行為に `Stealthily`、`reaches_unseen` でない操作に `SomeoneInTheDark`) は、行為を作るときにドメイン例外で断る。ツールの呼び方の誤りとして返す
- `SomeoneInTheDark` の相手は、行うときに世界がその場から選ぶ。暗さは知覚 (ステージ 5) の明るさで決まるので、共通の前提では確かめない。共通の前提を通ったあとに 1 回だけ、行う人と同じ場所にいる死んでいないほかの人 (倒れている人も入る。暗がりで触れうる) から `facts.random()` で選び (`ActionPrerequisiteCheck.cleared` → `ActionAttempt.aimed_in`)、以後の前提・効果・`PersonActedEvent`・`ActionAttemptFailedEvent` は相手の決まった試みを持つ。選べる人がいなければ共通の規則 `NoOneFoundInTheDark` として断る (#2148)

## 行為の型

```python
ObjectInteractionAttempt(actor: PersonId, obj: ObjectDeclaration, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
CarriedItemInteractionAttempt(actor: PersonId, item: ItemInstanceId, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)
PersonInteractionAttempt(actor: PersonId, target: PersonId | SomeoneInTheDark, interaction: InteractionDeclaration, arguments: ActionArguments, manner: Manner)

ItemUseAttempt(actor: PersonId, item: ItemInstanceId)
TendAttempt(actor: PersonId, target: PersonId)
ItemHandOverAttempt(actor: PersonId, to: PersonId, items: tuple[ItemInstanceId, ...], gold: Gold, manner: Manner)
# 品物かお金 (1G 以上) の少なくともどちらかを渡す。どちらも無ければ行為を作るときにドメイン例外 (形の誤り)。お金だけを渡してもよい (D2224)
# お金が足りなければ渡す途中で PersonInventory.pay が断る (INSUFFICIENT_GOLD)。品物もお金も渡さない
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
# 1 回で渡す相手は 1 人。相手が複数だと、見ていた人には 1 つの確定の範囲から最初に知覚した刺激しか届かないので、相手ごとに別の行為にする (#2152)
# 自分には渡せない。行う人自身を相手にすると、行為を作るときにドメイン例外で断る (形の誤り、#2147)
# 倒れている人と死んだ人は受け取れない。渡す途中で集約が断る (PERSON_NOT_ALIVE、#2147)
# 何も変わらない持ち替えは断る。もう手に持っている品物を手に持つと ITEM_ALREADY_HELD、荷にある品物をしまうと ITEM_NOT_HELD (#2147)
SomeoneInTheDark()      # 暗がりの見分けのつかない人。相手は世界がその場から選ぶ (1 人なら決まる)。真っ暗では人がいることも分からないので使えない
VoteFor(person: PersonId) | Abstain()   # world_progress の GroupDecision のものを使う

ActionArguments = Mapping[ArgumentName, TextArgumentValue | ItemInstanceId]
TextArgumentValue(text: str)            # 空でない文
# 操作の宣言の arguments (world_design.md) に従って外側が作る。品物はエージェントが呼び方で指し、外側が場面に見えている品物から ItemInstanceId を引いて入れる
# ArgumentName は value_object/ の 1 つを、条件・効果・行為が使う
```

物・品物・人への操作は、操作の宣言 (`InteractionDeclaration`) の欄 (`interaction_id`、`exertion`、`actor_requirement`、`allows_stealth`、`reaches_unseen`、`arguments`) を読んで性質を答える。

モンスターへの攻撃は `AttackMonsterAttempt(actor, monster: MonsterId)` ([monster.md](monster.md))。

## 店の行為

取引は店 1 つにまとめる (D2224)。店の型と集約は [world_state.md](world_state.md) の `Shop`。

```python
OpenShopAttempt(actor: PersonId, look: ShopLook)                 # いる場所に自分の店を開く
CloseShopAttempt(actor: PersonId)
EditShopLineAttempt(actor: PersonId, side: ShopLineSide, item_spec: ItemSpecDeclaration, count: Count, unit_price: Gold, note: ShopLineNote | NoNote)
    # その品目を、この値に書き換える。数を増やせば荷から預け、減らせば荷へ戻す。0 なら品目が消える
    # 買い取りでは、数 × 単価のお金を預ける。増やせば荷から払い、減らせば荷へ戻す
RewriteShopLookAttempt(actor: PersonId, look: ShopLook)          # 開いているあいだだけ
CollectFromShopAttempt(actor: PersonId)                          # 店が買い取って受け取った品を、全部荷へ移す
BuyFromShopAttempt(actor: PersonId, shop: ShopId, item_spec: ItemSpecDeclaration, count: Count, seen_unit_price: Gold)
SellToShopAttempt(actor: PersonId, shop: ShopId, item_spec: ItemSpecDeclaration, count: Count, seen_unit_price: Gold)

class ShopLineSide(Enum):                       # 店が売る品目か、買い取る品目か
    SELLING = "SELLING"
    BUYING = "BUYING"
ShopLook(text: str)                             # 空でない 1 行、80 文字まで。超えれば行為を作るときにドメイン例外
ShopLineNote(text: str)                         # 品目の説明の文。空でない 1 行、80 文字まで
```

- 自分の店に向けた買う・売ると、数が 0 の買う・売るは、行為を作るときにドメイン例外で断る (形の誤り)。行う人の店かは `ShopId` と行う人から分かる
- 開くのは、いまいる場所に開く。近くにいる必要は無い。まだ店が無ければ新しく開き、閉じた店があれば `Shop.reopen` に任せる。閉じた店が同じ場所ならそのまま再開し、別の場所なら、品目と受け取った品が空のときだけ店ごと移る
- 開く以外の持ち主の行為 (閉じる・品目を編集する・見た目を書き直す・引き取る) は、自分の店の場所にいるときだけできる (`WithShop`)。品目の編集と引き取りは、閉じた店でもできる (閉じた店から品とお金を引き上げるため)。見た目の書き直しは、開いているあいだだけ
- 買う・売るは、場面に見えている店 (`SeenShop`、[perception.md](perception.md)) だけを相手にできる。暗くて店が見えなければ候補に出ない
- 試みが持つ単価 (`seen_unit_price`) は、エージェントが場面で見た単価。届いたときに店の単価と違えば断る (`SHOP.PRICE_CHANGED`)。考えているあいだに値段が上がっても、知らずに払わないため
- 買う・売るは、全部できるか、何もしないか。在庫・買い取りの残り・預けたお金・買い手のお金・荷の空きのどれかが足りなければ断る
- 持ち主の行為のツールは、店を出せる場所 (`SpotDeclaration.allows_shops`) が 1 つも無い世界では一覧から消す (`ToolExposure`、`DeclaredNouns.has_shop_sites`)。店を出せない場所にいるときは、できない (`NotNow`) で出す。買う・売るのツールは、店を出せる場所も作者の店も無い世界では消す (`DeclaredNouns.has_shops`)

断る理由 (`WorldStateRefusal` の `RefusalCode`)。文は共通の部品の `refusal_texts.world_state` に書く。

| error_code | いつ | 例 |
|---|---|---|
| `GAME_WORLD.SHOP.NOT_A_SHOP_SITE` | 店を出せない場所で開こうとした | 坑道の奥でトムが店を開こうとする |
| `GAME_WORLD.SHOP.GOODS_LEFT_ELSEWHERE` | 品目か受け取った品の残った自分の店が、別の場所にある | 広場の閉じた店にパンを残したトムが、通りで開こうとする |
| `GAME_WORLD.SHOP.ALREADY_OPEN` | もう開いている店を開こうとした | |
| `GAME_WORLD.SHOP.CLOSED` | 閉じた店で買う・売る、閉じた店の見た目を書き直す | |
| `GAME_WORLD.SHOP.NOT_ENOUGH_STOCK` | 買う数が在庫より多い | パン 3 つを頼んで残りが 2 つ |
| `GAME_WORLD.SHOP.NOT_ENOUGH_WANTED` | 売る数が買い取りの残りより多い。作者の店では、預けたお金が足りない | 薬草 3 つを売ろうとして、買い取りの残りが 2 つ |
| `GAME_WORLD.SHOP.NOT_LISTED` | その品物の品目が無い | パンを売っていない店でパンを買う |
| `GAME_WORLD.SHOP.PRICE_CHANGED` | 見た単価と店の単価が違う | レナが 10G で見たあと、トムが 50G に上げた |
| `GAME_WORLD.SHOP.NOTHING_TO_COLLECT` | 受け取った品が無いのに引き取ろうとした | |
| `GAME_WORLD.INSUFFICIENT_GOLD` (いまのもの) | 買い手のお金、または買い取りに預けるお金が足りない | 20G のレナがパンを 3 つ買う |
| `GAME_WORLD.INVENTORY_FULL` (いまのもの) | 買った品・引き取る品・品目から戻す品が荷に入らない | |
| `GAME_WORLD.NOT_ENOUGH_ITEMS_OF_SPEC` (いまのもの) | 売る品・品目に預ける品を、足りるだけ持っていない | |

## 断られたとき

```python
@final
@dataclass(frozen=True)
class ActionRefusal:
    attempt: ActionAttempt
    reason: CommonRuleRefusal | PreconditionRefusal | WorldStateRefusal
    text: TextAboutPeople                   # 見る人ごとの呼び方への置き換えは、行った人に届けるところで行う

CommonRuleRefusal = ActorCannotAct | Busy | NotTogether | OutOfReach | TooTired | NotAllowedInThisStage | NoOneFoundInTheDark | NotCarrying
# Busy: 前の行為を行っているあいだ (話すことだけはできる)
# ActorCannotAct: 倒れている、結末が決まった、去った人に許されない行為 (ActorRequirement)
# OutOfReach: 区画の中からしか届かない物に、外から触ろうとした
# NotCarrying: 品物を使う・品物への操作で、その品物を持っていない

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
- 投票は、開いている集団の決定のうち、投票する人 (`voters`) に入っている決定だけを出す。入っていない人には、その決定があることも出さない。候補は、選ばれうる人 (`choices`) の全員 (自分も含む) と、`abstain_allowed` なら棄権。投票は場所に縛られないので、場面に見えているかを問わない (#2197)
  - 並びは、決定の宣言の順に決定ごとにまとめ、中は人の宣言の順、棄権はその決定の最後。毎ターン同じ順に並べる (design_decisions #1 のプレフィックスキャッシュ)。一覧の中では人への操作の後に置く
  - 投票だけは、前提に加えて集約 (`GroupDecision.ballot_refusal`) に受け付けるかを尋ね、断る票 (投票済みなど) を `WorldStateRefusal` と同じ文でできないに分ける。前提だけで分けると、投票済みの人の票が「できる」に出て、試すと断られる。判断は `cast` と同じ 1 か所にあるので、一覧のために書き直さない
  - 投票済みの人には、決定の候補をすべてできないで出す (いまできない行為を消さない、design_decisions #37)。死んで選ばれうる人から外れた人への票は消え、その人に入れていた票は戻るので、入れた人にはまた候補ができるで出る
  - 倒れて投票する人から外れた人には、起きてもその決定は出さない (外れた人を集約は覚えていない)
- 行為の対象の候補は、場面 (`VisibleSurroundings`) に出ているものに限る。「誰か」(`Unidentified`) には `SomeoneInTheDark` で行う。ターンごとに振り直す呼び方 (「人影1」) は、記憶に残った呼び方が次のターンで別のものを指すので使わない (design_decisions #3)
