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
        # WorldClock.advance → Whereabouts.advance_travels → PersonVitals.pass_time (全員)
        # → 状態異常 → 天候 → モンスター
        ...

class SettleWorldConditions:
    def __call__(self, command: SettleWorldConditionsCommand) -> None:
        # 出来事 → 反応 (真偽が変わったものだけ) → 終わりの判定
        # 同じ出来事は 1 tick に 1 回まで
        ...

class RunScheduledTurns:
    def __call__(self, command: RunScheduledTurnsCommand) -> None: ...

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

class DecideDeathOutcomeHandler(EventHandler[PersonDiedEvent]): ...
class PlaceDepartedPersonHandler(EventHandler[PersonDiedEvent]): ...   # 体は残し、去った人を体のある場所に置く
class ApplyWorldStageChangeHandler(EventHandler[WorldStageChangedEvent]): ...   # 出る段階の when_left、入る段階の when_entered
class ApplyGroupDecisionResultHandler(EventHandler[GroupDecisionReachedEvent | GroupDecisionUnresolvedEvent]): ...
class DeliverMissedNoticesHandler(EventHandler[PersonRevivedEvent]): ...
class RemoveDeadMonsterHandler(EventHandler[MonsterDiedEvent]): ...
```

## 1 つの行為のユースケースの流れ

```
1. ツール呼び出しを、行為の試みに変える (行動しながらの一言は、2 つ目の SpeechAttempt)
── CommandScope の中 (どこで断られても巻き戻す)
2. ActionPrerequisiteCheck.refusal
3. 行為ごとの前提 (InteractionDeclaration.precondition など)
4. 世界を変える (Effect.apply、または専用のモデルの集約)
   最後に、体を使う行為なら PersonVitals.exert、LatestActions.note
──
5. ドメインイベントを配る (ハンドラ、観測、trace)

断られたとき:
- 2 で断られた: 巻き戻し、ActionRefusal を返す
- 3 か 4 で断られた: 巻き戻し、別の範囲で LatestActions.note_failed_attempt (ActionAttemptFailedEvent)、ActionRefusal を返す
- どれも、次の tick に手番が来る
```
