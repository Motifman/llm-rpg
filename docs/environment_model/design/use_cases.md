# ユースケースとハンドラ (application)

```python
class OpenWorld:
    def __call__(self, command: OpenWorldCommand) -> None: ...

class AdvanceWorldTick:
    def __call__(self, command: AdvanceWorldTickCommand) -> None:
        # 1. PassWorldTime                → ハンドラを全部済ませる
        #    時間帯が変わったら TimeOfDayChangedEvent をためる。知らせの相手は、刺激に変えるときに tick の終わりの世界から選ぶ (D2330)
        # 2. SettleWorldConditions        → ハンドラを全部済ませる
        # 1 tick が現実の何秒かは実行の設定で決める
        ...

class PassWorldTime:
    def __call__(self, command: PassWorldTimeCommand) -> None:
        # WorldClock.advance → Whereabouts.advance_travels → PersonVitals.pass_time(now, death, hunger) (世界にいる人。PersonOutcomes.people_in_world)
        # → 品物の時間 (Lasts の時間が過ぎた品物を、持っている人の PersonInventory か置かれた場所の GroundItems から手放させ、Item.run_out)
        #   荷の品物は、世界にいる人の分だけ。結末が決まって世界から外れた人は、体も荷の品物も時間が止まる (D2211)
        #   店に預けた品と受け取った品も進める (Shop.let_run_out)。持ち主が世界から外れた店は止める (D2224)
        # → 天候 (Weather.pass_time。ChangesEvery の N の倍数の時刻だけ facts.random() から 1 回引く) → モンスター (湧きを確かめ、個体ごとに感じて動き、SoundsThisTick を空にする。monster.md)
        # 状態効果は #2014 で決めてから足す
        ...

class SettleWorldConditions:
    def __call__(self, command: SettleWorldConditionsCommand) -> None:
        # command.occasion は AFTER_WORLD_TIME_PASSED か AFTER_COMMAND
        # 落ち着くまで繰り返す:
        #   1. まだこの tick に発火していない出来事、反応、二人で合わせる操作の条件を、すべて同じ世界の状態で確かめる
        #      (反応は真偽が変わったものだけ。二人で合わせる操作は ScenarioProgress.joint_action_settlement を見る。D2173)
        #   2. 真になったものを宣言の順に発火する (出来事、反応、二人で合わせる操作の順)
        #   3. 1 つも発火しなければ終わる
        # → 終わりの判定 (きっかけは WorldConditionsSettling)。終わっていれば WorldEnding.end (WorldEndedEvent)
        # 物の状態や通路の決め直しも反応としてこの中に入る (別の段にしない)
        ...
```

`SettleWorldConditions` の決まり (#1978 の D2 / E2 / E3、#2145 で調整役と決めた):

- 発火 1 回ごとを、確定の範囲の中の小さな範囲 (`WorldSession.attempt_apart`、[persistence.md](persistence.md)) にする。集約が断ったら、その発火の書き換えだけを巻き戻し、`ScenarioProgress.note_happening_fired` / `note_reaction_fired` に断った理由を渡して「その回は起きた」と記録する。次の tick に試し直さない
- 記録のたびに `HappeningFiredEvent` / `ReactionFiredEvent` が出る。断った理由 (`refusal`) が trace の材料になる。出来事のイベントには、効果を当てる前の世界で選んだ `AnnouncementTo` の相手 (`audience`) と、`SightAt` / `SoundFrom` のための効果の前の人ごとの居場所 (`present`、`PeopleWhoWereThere`) が載る。場所の様子 (明るさ、通路) は `DeliverPerception` が確定した後の世界で決める (D2207)
- 断られた発火のイベントには相手も効果の前の居場所も載せない。何も変わっていないので、知らせると起きていないことを伝えてしまう
- 偶然を使う条件 (`requirements().uses_chance`) は、出来事・反応・終わりのどれも、時間を進めたあと (`AFTER_WORLD_TIME_PASSED`) だけ確かめる。コマンドのたびに確かめると、1 tick にくじを何度も引き、書いた確率より高くなる
- 出来事は `ScenarioProgress` が 1 tick に 1 回までにする。反応には tick ごとの帳簿が無いので、1 回の `SettleWorldConditions` の中で同じ反応は 1 回まで (断られた回も数える)。自分の条件を崩す反応 (鐘が鳴ったら止める、止んだら鳴らす) でも止まる。回る回数は出来事と反応と二人で合わせる操作の宣言の数を超えない
- 二人で合わせる操作は、帳簿が揃いか時間切れを返したものを発火する。当てる効果 (`on_complete` / `on_timeout`)、知らせ、きっかけ (`JointActionCompleted` / `JointActionTimedOut`) は `JointActionSettlement` が選ぶ。断られたら出来事と同じく巻き戻し、`ScenarioProgress.note_joint_action_settled` に理由を渡す。落ち着かせると帳簿が空になるので、1 回の落ち着かせに 1 回まで (D2173)
- 反応を初めて確かめたとき (帳簿に真偽が無いとき) は、真偽を記録するだけで発火しない。世界の始まりには何も変わっていない
- 終わりの判定のきっかけは `WorldConditionsSettling`。`WorldTimePassing` を流用すると、コマンドの後の判定が trace で「時間が進んだから終わった」と読めてしまう
- `ForEveryoneEffect` は 1 人ずつを小さな範囲にし、断られた人の分だけを巻き戻す。1 人の荷が満杯なだけで、ほかの全員がもらえなくなるのを避ける。1 人ごとの断りは、いまはイベントに載せない

```python
class DeliverPerceptionOfCommittedEvents:          # CommittedEventsDistributor の receiver。ハンドラより先に動く
    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        # OccurrencesInCommit.split でまとまりに分け (1 つの行為、1 回の発火、時の経過のイベント 1 つ。D2206)
        # → まとまりごとに StimulusTranslator で刺激に変え、行為のイベントの刺激と状態のイベントの刺激に分けて DeliverPerception
        # → 刺激が 1 つも無いまとまりは渡さない
        # 気を失ったまま結末が決まった人には、結末の知らせをここで MissedNotices にためてから、DeliverNoticesOnLeavingHandler が渡す。receiver がハンドラより先に動くことに頼る (D2203)
        ...

class DeliverPerception:
    def __call__(self, command: DeliverPerceptionCommand) -> None:
        # command は原因 (PerceptionCause) と刺激を持つ
        # 刺激ごとに知覚しうる人を選ぶ (見える: その場所にいる人。その場所にいる去った人を含む。聞こえる: SoundReach が届く場所の人)
        # 作者の場所の知らせと行為の知らせの刺激は、知覚する人を効果の前の居場所 (PeopleWhoWereThere) に置き直してから聞く (D2207、D2216)
        # → Perceiver と LightingConditions / SoundReach を作り、刺激の perceived_by に聞く
        # → 1 つの出来事の刺激は 本人の体 → 見える → 聞こえる → 世界の知らせ の順に聞き、本人の体・見える・聞こえるは 1 人にいちばん多くを伝えるものだけ (D2268-20)。世界の知らせは数えずに届ける (D2203)
        # → Perceived は観測の出口へ
        # → NoticedLater は MissedNotices.keep
        # → 音の刺激は、計算した SoundReach を SoundsThisTick.note にも書く (モンスターが次の tick に聞く)
        # → 確定したら、届けた記録 (PerceptionDeliveryReport。原因・tick・刺激・人ごとの結果と届かなかった理由) を受け口に渡す (D2206)
        ...

class LookAround:
    def __call__(self, command: LookAroundCommand) -> VisibleSurroundings:
        # SpotContents と LightingConditions を集め、VisibleSurroundings.seen_with
        # 物を集めるときに WorldDesign.looks_of(物).look_now で、いまの見え方を決める
        ...

class DeliverSurroundings:
    def __call__(self, command: DeliverSurroundingsCommand) -> None:
        # LookAround → VisibleSurroundings.perceived_by で人、倒れた体、モンスターを 1 つの観測にして出口へ。誰もいなければ渡さない
        ...

class DeliverNoticesOnWaking:                     # 介抱の確定のあと、別の確定の範囲で動く
    def __call__(self, command: DeliverNoticesOnWakingCommand) -> None:
        # 1. 起きたことの知らせ (本人の体の刺激) を DeliverPerception で配る。原因は Waking
        # 2. MissedNotices.perceived_on_waking (ためた順、目が覚めた時刻) を出口へ渡し、MissedNotices.clear
        # 3. DeliverSurroundings
        # 見渡した知らせが「目が覚めた」より先に記憶に入らないよう、この順に手順として置く
        # 気を失ったまま結末が決まって世界から外れる人にも、2. を同じ順で渡す。結末の知らせもためた知らせに入っている。目覚めていないので 1. と 3. は渡さない (D2203)
        ...

class ListAvailableActions:
    def __call__(self, command: ListAvailableActionsCommand) -> AvailableActions:
        # VisibleSurroundings に出ているものを対象の候補にし、試したときと同じ確認で分ける
        ...

class InteractWithObject:
    def __call__(self, command: InteractWithObjectCommand) -> ActionReply: ...

class InteractWithCarriedItem:
    def __call__(self, command: InteractWithCarriedItemCommand) -> ActionReply: ...

class InteractWithPerson:
    def __call__(self, command: InteractWithPersonCommand) -> ActionReply: ...

class UseItem:
    def __call__(self, command: UseItemCommand) -> ActionReply: ...

class TendFallenPerson:
    def __call__(self, command: TendFallenPersonCommand) -> ActionReply: ...   # WorldRules.tend.revive。倒れていなければ PersonVitals が断る

class HandOverItems:
    def __call__(self, command: HandOverItemsCommand) -> ActionReply: ...

class PickUpGroundItem:
    def __call__(self, command: PickUpGroundItemCommand) -> ActionReply: ...

class DropItem:
    def __call__(self, command: DropItemCommand) -> ActionReply: ...

class EnterSection:
    def __call__(self, command: EnterSectionCommand) -> ActionReply: ...   # 満員は Whereabouts が断る

class LeaveSection:
    def __call__(self, command: LeaveSectionCommand) -> ActionReply: ...

class HoldItem:
    def __call__(self, command: HoldItemCommand) -> ActionReply: ...

class PutAwayItem:
    def __call__(self, command: PutAwayItemCommand) -> ActionReply: ...

class SearchSpot:
    def __call__(self, command: SearchSpotCommand) -> ActionReply:
        # ドメインサービス SpotSearch: SpotSearchProgress.record_search → まだ見つけていない物の条件を確かめる → mark_found → when_found
        # 道の途中なら、移動と同じ OccupantNotAtRouteStartException (「今は道の途中だ。」) で断る
        ...

class AttackMonster:
    def __call__(self, command: AttackMonsterCommand) -> None: ...

# 店 (D2224)。どれも行為の共通の前提を通ってから集約を呼ぶ
class OpenShop:
    def __call__(self, command: OpenShopCommand) -> ActionReply: ...        # 店が無ければ Shop.open_at、あれば Shop.reopen

class CloseShop:
    def __call__(self, command: CloseShopCommand) -> ActionReply: ...

class EditShopLine:
    def __call__(self, command: EditShopLineCommand) -> ActionReply:
        # 売り: 増やす分を PersonInventory.items_to_give_up で選んで give_up → Shop.stock。減らす分は Shop.unstock → 戻る品を receive
        # 買い取り: 足すお金を PersonInventory.pay → Shop.post_wanted。戻るお金は earn
        ...

class RewriteShopLook:
    def __call__(self, command: RewriteShopLookCommand) -> ActionReply: ...

class BuyFromShop:
    def __call__(self, command: BuyFromShopCommand) -> ActionReply: ...      # ShopTrade.buy。代金を持ち主に入れるのも手順の中 (売り買いが果たせないため)

class SellToShop:
    def __call__(self, command: SellToShopCommand) -> ActionReply: ...       # ShopTrade.sell

class CollectFromShop:
    def __call__(self, command: CollectFromShopCommand) -> ActionReply: ...  # Shop.hand_over_received → 品を荷へ receive

class CloseShopOfGoneOwnerHandler:      # PersonDiedEvent / PersonOutcomeDecidedEvent (世界から外れた) を受け、その人の店を close_for_gone_owner
    ...

class StartTravel:
    def __call__(self, command: StartTravelCommand) -> ActionReply: ...

class Speak:
    def __call__(self, command: SpeakCommand) -> None: ...

class CastBallot:
    def __call__(self, command: CastBallotCommand) -> None: ...

# ハンドラ (どれも確定の後に、自分の巻き戻しの範囲で動く。互いの順番に頼らない)

class DecideDeathOutcomeHandler(EventHandler[PersonDiedEvent]): ...   # 結末を Died にする
class PlaceDepartedPersonHandler(EventHandler[PersonDiedEvent]): ...   # departed_persons_act の世界だけ。体は残し、去った人を体のある場所に置く
class ApplyWorldStageChangeHandler(EventHandler[WorldStageChangedEvent]): ...   # 出る段階の when_left、入る段階の when_entered
class ApplyGroupDecisionReachedHandler(EventHandler[GroupDecisionReachedEvent]): ...   # when_decided
class ApplyGroupDecisionUnresolvedHandler(EventHandler[GroupDecisionUnresolvedEvent]): ...   # when_undecided
class DeliverNoticesOnWakingHandler(EventHandler[PersonRevivedEvent]): ...   # DeliverNoticesOnWaking を呼ぶ
class DeliverSurroundingsOnArrivalHandler(EventHandler[OccupantEnteredSpotEvent]): ...   # 着いた本人について DeliverSurroundings を呼ぶ
class DeliverDarkeningHandler(EventHandler[ItemStateChangedEvent | ItemPutAwayEvent | ItemGivenUpEvent | TimeOfDayChangedEvent | WeatherChangedEvent | SpotAtmosphereChangedEvent]): ...
    # 明るさが下がった場所にいた人へ、「辺りが暗くなった」の見える刺激を DeliverPerception で配る
class DeliverSurroundingsOnBrighteningHandler(EventHandler[ItemStateChangedEvent | ItemHeldEvent | ItemPutAwayEvent | OccupantEnteredSpotEvent | TimeOfDayChangedEvent | WeatherChangedEvent | SpotAtmosphereChangedEvent]): ...
    # イベントが持つ前と後の値から、前後の LightingConditions を比べ、明るさが上がった場所にいた人ごとに DeliverSurroundings を呼ぶ
    # OccupantEnteredSpotEvent のときは、着いた本人を除く (DeliverSurroundingsOnArrivalHandler が渡す)
class WithdrawFromGroupDecisionHandler(EventHandler[PersonFellEvent | PersonDiedEvent]): ...
    # 開いている集団の決定から、死んだ人は先に withdraw_choice (その人に入った票を戻す)、続けて withdraw_voter。倒れた人は withdraw_voter だけ
class DropMonsterLootHandler(EventHandler[MonsterDiedEvent]): ...   # 死んだ場所の地面に落とす物を置く。死骸は湧きの present_while が偽になるまで残る
```

## 世界と外側

- 入口は、行為を受け付ける `AcceptAction` と、時間を進める要求を受け付ける `AcceptWorldTimePassage`。どちらも 1 回の呼び出しで 1 つを同期で確定させる。世界の側に待ち行列は持たない
- 届いた順に 1 つずつ呼ぶのも、同時に呼ばないのも、外側の責任
- 世界が終わったあとに届いた行為と時間を進める要求は、どちらも断り、世界を変えない。規則は `WorldEnding.admit_change` が持つ。行為には「世界はもう終わった」の文 (`RefusalTexts.world_state`) で `ActionRefused` を返し、断られた試みは記録しない。時間には `WorldTimePassageRefused` を返す。外側は、返事か `WorldHasEnded` で終わりを知る (D2218)
- 世界がするのは、コマンドを届いた順に 1 つずつ確定させること (1 つのコマンドの確定が 1 つの `CommandScope`。終わっていないかの確かめと `SettleWorldConditions` は、それぞれ別の範囲) と、時間を進めること (`AdvanceWorldTick`) だけ。同時に最後の 1 席を取りに来たら、先に確定したほうが通る
- `SettleWorldConditions` は、1 つのコマンドが確定するたびと、時間を進めるたびに回す
- Being が世界に入るとき、外側は問い合わせ `BriefEnteringPerson` に、その人と立場 (`CharacterBriefing.known_facts`)・目的 (`CharacterBriefing.objective`) を渡す。世界は、導入 (`WorldIntroduction.text`)、世界の前提 (`WorldIntroduction.premises`)、立場を、`BriefingHeadings` の見出しの違う `Description` にした案内 (`Orientation`) と、課す目的の文と、最初から知っている人 (`knows_at_start`) を返す。外側は、知っている人を Being の名前に変えて紹介 (`EnvironmentEntry.introductions`) にし、目的を課された目的 (`EnvironmentEntry.imposed_goal`) で渡す。世界は Being の名前を知らないため (D2222、#2229)
- 外側は、Being を世界に入れる前に、入口 `NamePerson` で Being の名前を世界の名簿 (`PeopleRegister`) に付ける。名前を付けていない人が出てくる観測は作れない (D2229-3)
- 昼夜を宣言しない世界 (`NoDayNight`) は、ステージ 8 では run の入口で `is_declared()` を確かめて止め、知らせる。観測の時刻を割り出せないため (D2222)
- 誰がいつ考えて行動を送るか (手番、目立つ知らせで考え直す、しばらく何も無ければ考える) は世界の外側 (エージェントを動かす側) が決める。今の実験のターン制は、外側の進め方の 1 つ

## 1 つの行為のユースケースの流れ

```
1. ツール呼び出しを、行為の試みに変える (行動しながらの一言は、2 つ目の SpeechAttempt)
   変えられなければ (無いツール名、場面に無い呼び方) TurnGuidance をコマンドへの返事として返して終わる
── CommandScope の中 (1 つの確定の範囲。どこで断られても全部巻き戻す)
2. ActionPrerequisiteCheck.cleared (行っているあいだは Busy。話すことだけはできる。通ったら暗がりの誰かに向けた相手をその場から選ぶ)
3. 行為ごとの前提 (InteractionDeclaration.precondition など)
4. 世界を変える (Effect.apply、または専用のモデルの集約)
   世界を変える前に、行う人の状況 (ActorSituation.of) と、人ごとの居場所 (PeopleWhoWereThere.before_the_effect) を読む (D2216)
   最後に、体を使う行為なら PersonVitals.exert、PersonVitals.start_action (行っているあいだ)、LatestActions.note (PersonActedEvent。効果の前の居場所を present に載せる)、
   ScenarioProgress.note_joint_action_part_done (どの二人で合わせる操作のどの部分に当たるかは帳簿が決める。D2173)
──
5. ドメインイベントを配る (DeliverPerceptionOfCommittedEvents → StimulusTranslator → DeliverPerception、ハンドラ、trace)
6. SettleWorldConditions (別の範囲。断られたときも回す)
7. コマンドへの返事 (通った / 断られた理由) を返す

1 と 2 のあいだで、`AcceptAction` が世界が終わっていないかを確かめる。2〜5 は行為ごとのユースケースを呼べば済み、6 と 7 は `AcceptAction` が受け持つ。2〜4 と断られたときは、共通の流れ `CarryOutAction` が受け持つ。行為ごとのユースケースは、行為の試みを持つコマンド (`StartTravelCommand(attempt: TravelAttempt)` など) を受け、`ActionSteps` の 2 つ (3 の `unmet_precondition` と、4 で世界を変えて行っているあいだの長さを返す `change_world`) だけを書く。返事は `ActionDone()` か `ActionRefused(refusal: ActionRefusal)` (#2146)

```python
class ActionSteps(Protocol[_Attempt]):
    def unmet_precondition(self, attempt: _Attempt, facts: WorldFacts) -> FailureReason | HiddenFailure | None: ...
    def change_world(self, attempt: _Attempt, facts: WorldFacts, world: WorldAggregates) -> Ticks: ...
```

- 体を使う行為だけ疲れ、行為の長さのあいだは体を使わない行為でも行っている (`PersonVitals.start_acting`)。去った人は疲れず、行っているあいだも持たない。行っている最中に始めた行為 (話すこと) は、いまの行為の終わりを早めない
- 集約が断ったとして返すのは、世界の断りの印 `WorldRefusal` のある例外だけ。印の無いドメイン例外は誤りとして投げ直し、run を止める (#2165、D2081)
- 集約が断った理由の文は `RefusalTexts.world_state` から引き、表に無ければ `RefusalTexts.unlisted` を使う。例外の文面は返さない (品物の ID が入る)

断られたとき (2 か 3 か 4):
- 巻き戻し、別の範囲で LatestActions.note_failed_attempt (ActionAttemptFailedEvent)。巻き戻したあとなので、いまの居場所が効果の前の居場所と同じになり、present は載せない (D2216)
- コマンドへの返事として断られた理由を返し、本人の記憶にも、変換役が ActionAttemptFailedEvent から作る本人の体の刺激 (断られた理由の文) が届く
- 見ていた人に届くのは 3 か 4 で断られ、作者が失敗の目撃の文 (`PerceptionDeclaration.on_failure`) を書いたときだけ。2 は周りから見て何も起きていない
```

## 刺激への変換と、観測の出口

```python
class StimulusTranslator:                         # ドメインイベントの種類ごと。今の formatter の後継
    def stimuli_of(self, event: DomainEvent, design: WorldDesign) -> tuple[Stimulus, ...]: ...
        # 行為の目撃は PersonActedEvent から、失敗は ActionAttemptFailedEvent から作る
        # 着いたことは OccupantEnteredSpotEvent から arrival の文で、品物の時間切れは ItemRanOutEvent から Lasts.ended_text で作る
        # 作者が宣言した操作や出来事は宣言の文を使い、どの世界にもある行為 (拾う、移動するなど) はシナリオの BuiltInActionPerceptions の文を使う
        # コードに決まった文を持たない
        # 受け手を決める、暗さで文を変える、はしない
        # 世界を読まない。要る値 (起きた場所、来た場所、品物の種類) は、起きた時点でイベントに載せる。確定したあとの世界は、移動や使い切りで変わっているため
        # 刺激を作らない種類は NOT_PERCEIVED_EVENT_KINDS に明示し、変換にも一覧にも無い種類は止める。振り分けの漏れはアーキテクチャのテストで見張る (#2152)
        # teleport で着いたときは、来た場所が無いので刺激を作らない
        # 断られた行為は、本人には断られた理由の体の刺激 (Background)。見ていた人には、前提か世界を変える途中で断られ、作者が on_failure を書いたときだけ
        # 去った人には体が無いので、断られた理由の体の刺激は届かない。理由はコマンドへの返事にだけ出て、外側が「自分の行動の結果」として渡す
        # 出来事の発火は happening_id で宣言の notice を引く。世界の知らせの相手はイベントに載った相手。断られた発火は作らない。反応は知らせを持たないので作らない
        # 二人で合わせる操作の揃い・時間切れは joint_id で宣言の complete_notice / timeout_notice を引く。相手と断られたときは出来事と同じ
```

```python
@final
@dataclass(frozen=True)
class TurnGuidance:                               # 世界では何も起きていない。ツールの呼び方の誤り。コマンドへの返事として返し、観測にはしない
    person: PersonId
    text: str
    at: WorldTick
```

- 観測の出口は 1 つ。`Perceived` と、倒れている間にためた知らせだけを受け、時刻の札を付けて Being の契約の観測にする。時刻の札は何日目と時:分 (`2 日目 06:30`) で、`DayNightDeclaration.day_and_clock_time_at` が返す `DayAndClockTime` から作る (D2222)。文は `TextWithAssignedPeople` のまま渡し、人のプレースホルダーは Being が覚えた名前か見た目で埋める
- 外側がエージェントに考えさせる前に集める材料は 3 つに分かれる。場面 (`LookAround`)、できること (`ListAvailableActions`)、自分が知っていること (持ち物、体の状態、時刻。知覚を通さず集約から読む)

## そのほかの型

- `CommandScope`: 1 つの確定の範囲。`WorldStore.session()` で 1 つのトランザクションを始め、中で断られたら `roll_back` で全部巻き戻す。確定したら `commit` が返したイベントを配る ([persistence.md](persistence.md))
- `DesignLocation(declaration: str, name: str, field: str, file: ScenarioFile | NoScenarioFile)`: 宣言の中の場所。宣言の種類、名前、欄 (`"object"`, `"lift_lever"`, `"state_keys[0]"`) と、どのファイルに書いたか (シナリオか、取り込んだどの共通の部品か)。ファイルは読み込む側が付け、ドメインが照らし合わせて見つけた誤りは `NoScenarioFile` で作る。シナリオを作る LLM が誤りを直すときに、どのファイルのどこを直せばよいかが分かるようにする (#2057)
- `RefusalCode`: ドメイン例外の `error_code` (`WHEREABOUTS.SECTION_FULL` など)
- `HandsNeeded`: 1 か 2
