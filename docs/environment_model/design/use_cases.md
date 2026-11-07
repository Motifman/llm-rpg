# ユースケースとハンドラ (application)

```python
class OpenWorld:
    def __call__(self, command: OpenWorldCommand) -> None: ...

class AdvanceWorldTick:
    def __call__(self, command: AdvanceWorldTickCommand) -> None:
        # 1. PassWorldTime                → ハンドラを全部済ませる
        # 2. SettleWorldConditions        → ハンドラを全部済ませる
        # 3. 終わっていれば止める
        # 4. RunScheduledTurns (1 人ずつ。1 人ごとに → ハンドラを全部済ませる)
        # 5. SettleWorldConditions        → ハンドラを全部済ませる
        ...

class PassWorldTime:
    def __call__(self, command: PassWorldTimeCommand) -> None:
        # WorldClock.advance → Whereabouts.advance_travels → PersonVitals.pass_time(now, death, hunger) (全員)
        # → 状態異常 → 天候 → モンスター
        ...

class SettleWorldConditions:
    def __call__(self, command: SettleWorldConditionsCommand) -> None:
        # 落ち着くまで繰り返す:
        #   1. まだこの tick に発火していない出来事、反応、二人で合わせる操作の条件を、すべて同じ世界の状態で確かめる
        #      (反応は真偽が変わったものだけ。二人で合わせる操作は LatestActions を見る)
        #   2. 真になったものを宣言の順に発火する
        #   3. 1 つも発火しなければ終わる
        # → 終わりの判定
        # どれも 1 tick に 1 回までなので、回る回数は宣言の数を超えない
        # 物の状態や通路の決め直しも反応としてこの中に入る (別の段にしない)
        ...

class RunScheduledTurns:
    def __call__(self, command: RunScheduledTurnsCommand) -> None:
        # 手番を取れる人 (起きている人と、去った人の手番がある世界の去った人。移動中は除く) を決め、
        # PendingTurns.take_due で手番の来た人を決めて、1 人ずつ手番を回す
        ...

class DeliverPerception:
    def __call__(self, command: DeliverPerceptionCommand) -> None:
        # 刺激ごとに知覚しうる人を選ぶ (見える: その場所にいる人。その場所にいる去った人を含む。聞こえる: SoundReach が届く場所の人)
        # → Perceiver と LightingConditions / SoundReach を作り、刺激の perceived_by に聞く
        # → 1 つの出来事の刺激は 本人の体 → 見える → 聞こえる → 世界の知らせ の順に聞き、1 人には最初に知覚したものだけ
        # → Perceived は観測の出口へ。calls_attention なら PendingTurns.call、どれも PendingTurns.note_activity
        # → NoticedLater は MissedNotices.keep
        ...

class LookAround:
    def __call__(self, command: LookAroundCommand) -> VisibleSurroundings:
        # SpotContents と LightingConditions を集め、VisibleSurroundings.seen_with
        ...

class DeliverSurroundings:
    def __call__(self, command: DeliverSurroundingsCommand) -> None:
        # LookAround → 人、倒れた体、モンスターを 1 つの観測にして出口へ
        ...

class DeliverNoticesOnWaking:
    def __call__(self, command: DeliverNoticesOnWakingCommand) -> None:
        # 1. 起きたことの知らせ (本人の体の刺激) を DeliverPerception で配る
        # 2. MissedNotices の知らせを古い順に出口へ渡し、MissedNotices.clear
        # 3. DeliverSurroundings
        # 見渡した知らせが「目が覚めた」より先に記憶に入らないよう、この順に手順として置く
        ...

class ListAvailableActions:
    def __call__(self, command: ListAvailableActionsCommand) -> AvailableActions:
        # VisibleSurroundings に出ているものを対象の候補にし、試したときと同じ確認で分ける
        ...

class InteractWithObject:
    def __call__(self, command: InteractWithObjectCommand) -> None: ...

class InteractWithCarriedItem:
    def __call__(self, command: InteractWithCarriedItemCommand) -> None: ...

class InteractWithPerson:
    def __call__(self, command: InteractWithPersonCommand) -> None: ...

class UseItem:
    def __call__(self, command: UseItemCommand) -> None: ...

class TendFallenPerson:
    def __call__(self, command: TendFallenPersonCommand) -> None: ...

class HandOverItems:
    def __call__(self, command: HandOverItemsCommand) -> None: ...

class PickUpGroundItem:
    def __call__(self, command: PickUpGroundItemCommand) -> None: ...

class DropItem:
    def __call__(self, command: DropItemCommand) -> None: ...

class EnterSection:
    def __call__(self, command: EnterSectionCommand) -> None: ...   # 時間を使わない。満員は Whereabouts が断る

class LeaveSection:
    def __call__(self, command: LeaveSectionCommand) -> None: ...

class SearchSpot:
    def __call__(self, command: SearchSpotCommand) -> None:
        # SpotSearchProgress.record_search → 見つかる物の条件を確かめる → mark_found → when_found
        ...

class AttackMonster:
    def __call__(self, command: AttackMonsterCommand) -> None: ...

class StartTravel:
    def __call__(self, command: StartTravelCommand) -> None: ...

class Speak:
    def __call__(self, command: SpeakCommand) -> None: ...

class CastBallot:
    def __call__(self, command: CastBallotCommand) -> None: ...

# ハンドラ (どれも確定の後に、自分の巻き戻しの範囲で動く。互いの順番に頼らない)

class DecideDeathOutcomeHandler(EventHandler[PersonDiedEvent]): ...   # 結末を Died にする
class PlaceDepartedPersonHandler(EventHandler[PersonDiedEvent]): ...   # 体は残し、去った人を体のある場所に置く
class ApplyWorldStageChangeHandler(EventHandler[WorldStageChangedEvent]): ...   # 出る段階の when_left、入る段階の when_entered
class ApplyGroupDecisionResultHandler(EventHandler[GroupDecisionReachedEvent | GroupDecisionUnresolvedEvent]): ...
class DeliverNoticesOnWakingHandler(EventHandler[PersonRevivedEvent]): ...   # DeliverNoticesOnWaking を呼ぶ
class DeliverSurroundingsOnArrivalHandler(EventHandler[OccupantEnteredSpotEvent]): ...   # 着いた本人について DeliverSurroundings を呼ぶ
class DeliverSurroundingsOnBrighteningHandler(EventHandler[ItemStateChangedEvent | OccupantEnteredSpotEvent | TimeOfDayChangedEvent | WeatherChangedEvent | SpotAtmosphereChangedEvent]): ...
    # 出来事の前後の LightingConditions を比べ、明るさが上がった場所にいた人ごとに DeliverSurroundings を呼ぶ
class WithdrawFromGroupDecisionHandler(EventHandler[PersonFellEvent | PersonDiedEvent]): ...
    # 開いている集団の決定から、倒れた人と死んだ人を withdraw_voter。死んだ人は withdraw_choice も
class RemoveDeadMonsterHandler(EventHandler[MonsterDiedEvent]): ...
```

## 1 つの行為のユースケースの流れ

```
1. ツール呼び出しを、行為の試みに変える (行動しながらの一言は、2 つ目の SpeechAttempt)
   変えられなければ (無いツール名、場面に無い呼び方) TurnGuidance を出口へ渡して終わる
── CommandScope の中 (1 つの確定の範囲。どこで断られても全部巻き戻す)
2. ActionPrerequisiteCheck.refusal
3. 行為ごとの前提 (InteractionDeclaration.precondition など)
4. 世界を変える (Effect.apply、または専用のモデルの集約)
   最後に、体を使う行為なら PersonVitals.exert、LatestActions.note (PersonActedEvent)
──
5. ドメインイベントを配る (ハンドラ、StimulusTranslator → DeliverPerception、trace)

断られたとき (2 か 3 か 4):
- 巻き戻し、別の範囲で LatestActions.note_failed_attempt (ActionAttemptFailedEvent)
- 本人には、変換役が ActionAttemptFailedEvent から作る本人の体の刺激 (断られた理由の文) が届く。本人が関わるので手番が起きる
- 見ていた人に届くのは 3 か 4 で断られ、作者が失敗の目撃の文を書いたときだけ。2 は周りから見て何も起きていない
```

## 刺激への変換と、観測の出口

```python
class StimulusTranslator:                         # ドメインイベントの種類ごと。今の formatter の後継
    def stimuli_of(self, event: DomainEvent, design: WorldDesign) -> tuple[Stimulus, ...]: ...
        # 行為の目撃は PersonActedEvent から、失敗は ActionAttemptFailedEvent から作る
        # 作者が宣言した操作や出来事は宣言の文を使い、どの世界にもあるものは決まった文を作る
        # 受け手を決める、暗さで文を変える、手番を起こすかを決める、はしない
```

```python
@final
@dataclass(frozen=True)
class TurnGuidance:                               # 世界では何も起きていない。ツールの呼び方の誤り
    person: PersonId
    text: str
    at: WorldTick
```

- 観測の出口は 1 つ。`Perceived`、倒れている間にためた知らせ、`TurnGuidance` だけを受け、時刻の札を付けて Being の契約の観測にする。文は `TextWithPeople` のまま渡し、人の穴は Being が覚えた名前か見た目で埋める
- 手番の前のプロンプトの材料は 3 つに分かれる。場面 (`LookAround`)、できること (`ListAvailableActions`)、自分が知っていること (持ち物、体の状態、時刻。知覚を通さず集約から読む)
