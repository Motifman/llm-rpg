"""ターンの終わりに Jev を 1 回だけ呼び、予期の形と当否を問うて清算する (#1440)。

## 形の問いと清算の問いを分ける

このターンに書いた予期には形を、清算待ちの予期には当否を問う。1 問に混ぜると、
材料がまだ無い時点ではすべて「まだ分からない」に倒れ、崩れた予期を見分けられ
なかった (#1436 の試し)。どちらも同じ state を見るので、1 回の呼び出しにまとめる。

## 判定は既定値で埋めない

判断が得られないターンは、どの予期にも判定を渡さずに飛ばす (design_decisions 5)。
期限と件数の上限で閉じるのは判断ではなくターン数で決まるので、問う前に済ませる。

## 根拠は形と同じ呼び出しで問う

予期を書いたターンには、頭にあった信念とエピソードごとに、その予期の材料に
なったかも問う (#1484)。形と同じ予期を同じ state で見るので、呼び出しは増やさ
ない。選ばれたものだけを根拠として形と一緒に予期へ渡し、確定した当否はそこに
だけ返る。

## 発言の中身だけでは当たりにしない

発言は、その人がそう言ったという事実にすぎない。清算待ちの予期ごとに、当たりの
決め手が発言の中身しかないかを同じ呼び出しで問い、当たりでその確率が閾値を超え
たら「まだ分からない」として記録する (#1568)。問いの文で伝えるだけでは、Jev が
従わなかったことを結果からも trace からも見分けられない。

## 状態の変化を保存してから配る

集約が返した出来事は、予期と同じ保存の単位で未配信として積み (design_decisions
D1439)、保存し終えてから配り手に渡す。配る途中で失敗しても、確定した予期の
出来事は失われない。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventDispatcher,
)
from ai_rpg_world.application.being.expectation.grounds import (
    GroundsPlan,
    InMindTextReader,
    ground_question,
    plan_ground_questions,
)
from ai_rpg_world.application.being.expectation.likelihood_labels import (
    LIKELIHOOD_LABELS,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    NoulQuestion,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
    ExpectationSettled,
)
from ai_rpg_world.domain.memory.expectation.repository.expectation_repository import (
    ExpectationRepository,
)
from ai_rpg_world.domain.memory.expectation.value_object.check import Check
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    CheckVerdict,
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.expectation.value_object.shape_verdict import (
    ShapeVerdict,
)

SCENE_QUESTION = "scene_changed"
SKIPPED_NOTHING_TO_JUDGE = "nothing_to_judge"
SKIPPED_JUDGMENT_UNAVAILABLE = "judgment_unavailable"
SKIPPED_SETTLEMENT_FAILED = "settlement_failed"
# 根拠の閾値 (design_decisions D1484) と同じく、stub の迷った答え 0.5 ちょうどは採らない。
HEARSAY_ONLY_THRESHOLD = 0.5


@dataclass(frozen=True)
class TurnMaterial:
    """本人の 1 ターンのあいだに届いた出来事。行動と発言を分けて持つ。

    文は名前で書き、環境の ID を入れない。Jev の state にそのまま載る。
    """

    actions: tuple[str, ...] = ()
    speeches: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("actions", "speeches"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not all(
                isinstance(text, str) for text in value
            ):
                raise TypeError(f"{name} must be tuple[str, ...]")


@dataclass(frozen=True)
class SettlementReport:
    """1 ターンの清算で起きたこと。trace と同じ中身を呼び出し側にも返す。"""

    turn: int
    judged: bool
    skipped_reason: str | None
    transitions: tuple[Mapping[str, Any], ...] = ()
    scene_changed: float | None = None


@dataclass
class _Asked:
    kind: str
    expectation: Expectation | None = None
    ground_id: str | None = None
    hearsay_question: str | None = None


@dataclass
class _Turn:
    turn: int
    material: TurnMaterial
    transitions: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] | None = None


class ExpectationSettlementService:
    """Being の 1 手を受け取ったターンの終わりに、清算待ちと新しい予期を Jev に問う。

    時系列はこの service が Being ごとに直近 ``timeline_turns`` ターン分だけ持つ。
    snapshot には載せないので、再開した直後の数ターンは時系列が短い。
    """

    def __init__(
        self,
        repository: ExpectationRepository,
        *,
        judgment_port: ITypedJudgmentPort,
        dispatcher: ExpectationEventDispatcher,
        max_open: int,
        timeline_turns: int,
        grounds_reader: InMindTextReader,
        max_grounds_questions: int,
        grounds_min_probability: float,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        if not isinstance(repository, ExpectationRepository):
            raise TypeError("repository must be ExpectationRepository")
        if not isinstance(judgment_port, ITypedJudgmentPort):
            raise TypeError("judgment_port must be ITypedJudgmentPort")
        if not isinstance(dispatcher, ExpectationEventDispatcher):
            raise TypeError("dispatcher must be ExpectationEventDispatcher")
        if not isinstance(grounds_reader, InMindTextReader):
            raise TypeError("grounds_reader must be InMindTextReader")
        if isinstance(grounds_min_probability, bool) or not isinstance(
            grounds_min_probability, (int, float)
        ):
            raise TypeError("grounds_min_probability must be a number")
        if not 0.0 < float(grounds_min_probability) < 1.0:
            raise ValueError("grounds_min_probability must be in (0, 1)")
        for name, value in (
            ("max_open", max_open),
            ("timeline_turns", timeline_turns),
            ("max_grounds_questions", max_grounds_questions),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be int")
            if value < 1:
                raise ValueError(f"{name} must be 1 or greater")
        self._repository = repository
        self._port = judgment_port
        self._dispatcher = dispatcher
        self._max_open = max_open
        self._timeline_turns = timeline_turns
        self._grounds_reader = grounds_reader
        self._max_grounds_questions = max_grounds_questions
        self._grounds_min_probability = float(grounds_min_probability)
        self._trace_recorder_provider = trace_recorder_provider
        self._timelines: dict[BeingId, deque[_Turn]] = {}

    def settle_turn(
        self,
        being_id: BeingId,
        *,
        self_name: str,
        material: TurnMaterial,
        tick: int | None = None,
        player_id: int | None = None,
    ) -> SettlementReport:
        """いまのターン数で清算し、保存のあとで未配信の出来事を配る。

        同じターンに 2 回呼ぶと ``ValueError``。照合は 1 ターンに 1 回までなので、
        2 回目を黙って飛ばすと、ターン数を進め忘れた配線に気づけない。

        途中で例外が出たときは、それまでに閉じた予期と理由を trace に残し、保存
        済みの出来事を配ってから投げ直す。期限と件数で閉じた予期は問う前に保存
        しているので、trace に残さないと閉じたことが見えなくなる。
        """
        if not isinstance(material, TurnMaterial):
            raise TypeError("material must be TurnMaterial")
        current = _Turn(turn=self._repository.current_turn(being_id), material=material)
        try:
            return self._settle(being_id, self_name, current, tick, player_id)
        except Exception as exc:
            report = SettlementReport(
                turn=current.turn,
                judged=False,
                skipped_reason=SKIPPED_SETTLEMENT_FAILED,
                transitions=tuple(current.transitions),
            )
            self._trace(
                being_id,
                report,
                tick,
                player_id,
                state=current.state,
                unavailable_reason=f"{type(exc).__name__}: {exc}",
            )
            self._dispatcher.deliver_pending(being_id, tick=tick, player_id=player_id)
            raise

    def _settle(
        self,
        being_id: BeingId,
        self_name: str,
        current: _Turn,
        tick: int | None,
        player_id: int | None,
    ) -> SettlementReport:
        now = current.turn
        timeline = self._timelines.setdefault(
            being_id, deque(maxlen=self._timeline_turns)
        )
        if timeline and timeline[-1].turn >= now:
            raise ValueError(
                f"turn {now} of {being_id} has already been settled; "
                "advance_turn must be called once per move"
            )
        timeline.append(current)

        pending, new = self._close_by_turn_count(being_id, current)
        if not pending and not new:
            report = SettlementReport(
                turn=now,
                judged=False,
                skipped_reason=SKIPPED_NOTHING_TO_JUDGE,
                transitions=tuple(current.transitions),
            )
            self._trace(being_id, report, tick, player_id)
            self._dispatcher.deliver_pending(being_id, tick=tick, player_id=player_id)
            return report

        plan = plan_ground_questions(
            being_id, new, reader=self._grounds_reader, limit=self._max_grounds_questions
        )
        asked, questions = _questions(self_name, pending=pending, new=new, plan=plan)
        state = _state(self_name, now=now, pending=pending, new=new, timeline=timeline)
        current.state = state
        try:
            answers = self._port.judge(state, questions)
            verdicts = _verdicts(asked, answers)
        except TypedJudgmentUnavailableException as exc:
            report = SettlementReport(
                turn=now,
                judged=False,
                skipped_reason=SKIPPED_JUDGMENT_UNAVAILABLE,
                transitions=tuple(current.transitions),
            )
            self._trace(
                being_id,
                report,
                tick,
                player_id,
                state=state,
                asked=asked,
                grounds=plan.trace(answers=None, judged=None),
                unavailable_reason=f"{exc.error_code}: {exc}",
            )
            self._dispatcher.deliver_pending(being_id, tick=tick, player_id=player_id)
            return report

        probabilities = {
            name: verdict for name, verdict in verdicts.items() if isinstance(verdict, float)
        }
        judged_grounds: dict[str, ExpectationGrounds] = {}
        for name, verdict in verdicts.items():
            if isinstance(verdict, float):
                continue
            expectation = asked[name].expectation
            assert expectation is not None
            event: ExpectationEvent | None
            downgraded: dict[str, Any] = {}
            if isinstance(verdict, ShapeVerdict):
                grounds = plan.grounds_for(
                    expectation, probabilities, self._grounds_min_probability
                )
                event = expectation.judge_shape(verdict, turn=now, grounds=grounds)
                judged_grounds[expectation.expectation_id.value] = grounds
                step = "shape"
            else:
                hearsay_question = asked[name].hearsay_question
                assert hearsay_question is not None
                hearsay_only = probabilities[hearsay_question]
                if verdict is CheckVerdict.HIT and hearsay_only > HEARSAY_ONLY_THRESHOLD:
                    downgraded = {"judged_verdict": verdict.value, "hearsay_only": hearsay_only}
                    verdict = CheckVerdict.UNDETERMINED
                event = expectation.record(Check(turn=now, verdict=verdict))
                step = "check"
            self._save(current, expectation, event, step=step, verdict=verdict)
            current.transitions[-1].update(downgraded)

        report = SettlementReport(
            turn=now,
            judged=True,
            skipped_reason=None,
            transitions=tuple(current.transitions),
            scene_changed=float(answers[SCENE_QUESTION].value),
        )
        self._trace(
            being_id,
            report,
            tick,
            player_id,
            state=state,
            asked=asked,
            answers=answers,
            grounds=plan.trace(answers=answers, judged=judged_grounds),
        )
        self._dispatcher.deliver_pending(being_id, tick=tick, player_id=player_id)
        return report

    def _close_by_turn_count(
        self, being_id: BeingId, current: _Turn
    ) -> tuple[list[Expectation], list[Expectation]]:
        """期限を過ぎた予期と、件数の上限を超えた予期を閉じ、残りを清算待ちと新しい予期に分ける。"""
        now = current.turn
        pending: list[Expectation] = []
        new: list[Expectation] = []
        for expectation in self._repository.list_open_by_being(being_id):
            event = expectation.expire_if_overdue(now_turn=now)
            if event is not None:
                self._save(current, expectation, event, step="overdue")
            elif expectation.awaits_shape:
                new.append(expectation)
            else:
                pending.append(expectation)

        overflow = len(pending) - self._max_open
        if overflow > 0:
            # 期日の無い予期は、届く出来事のどれで決まるかが読みにくく、長く
            # 「まだ分からない」に留まりやすい。期日のある予期は期日が近づけば決まる。
            order = sorted(
                pending, key=lambda e: (e.due is not None, e.formed_at_turn)
            )
            for expectation in order[:overflow]:
                event = expectation.expire_early(now_turn=now)
                self._save(current, expectation, event, step="over_capacity")
                pending.remove(expectation)
        return pending, new

    def _save(
        self,
        current: _Turn,
        expectation: Expectation,
        event: ExpectationEvent | None,
        *,
        step: str,
        verdict: ShapeVerdict | CheckVerdict | None = None,
    ) -> None:
        if isinstance(event, ExpectationSettled) and event.outcome is Outcome.MISS:
            event = replace(
                event,
                what_happened=_what_happened(
                    self._timelines.get(expectation.holder, ()),
                    since=expectation.formed_at_turn,
                    until=current.turn,
                ),
            )
        self._repository.save(expectation, [] if event is None else [event])
        transition: dict[str, Any] = {
            "expectation_id": expectation.expectation_id.value,
            "step": step,
            "verdict": None if verdict is None else verdict.value,
            "event": None if event is None else type(event).__name__,
            "status_after": expectation.snapshot().status.value,
        }
        if isinstance(event, ExpectationSettled) and event.outcome is Outcome.MISS:
            # 時系列は直近の数ターンしか持たず、再開直後は空になる。外れの材料が理由を
            # 持たなかったことを、書いたターンと時系列の最初のターンで読めるようにする。
            timeline = self._timelines.get(expectation.holder, ())
            transition["what_happened_lines"] = len(event.what_happened)
            transition["formed_at_turn"] = expectation.formed_at_turn
            transition["timeline_from_turn"] = timeline[0].turn if timeline else None
        current.transitions.append(transition)

    def _trace(
        self,
        being_id: BeingId,
        report: SettlementReport,
        tick: int | None,
        player_id: int | None,
        *,
        state: Mapping[str, Any] | None = None,
        asked: Mapping[str, _Asked] | None = None,
        answers: Mapping[str, JudgmentResult] | None = None,
        grounds: list[dict[str, Any]] | None = None,
        unavailable_reason: str | None = None,
    ) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.EXPECTATION_SETTLEMENT,
            tick=tick,
            player_id=player_id,
            being_id=being_id.value,
            turn=report.turn,
            judged=report.judged,
            skipped_reason=report.skipped_reason,
            unavailable_reason=unavailable_reason,
            state=None if state is None else dict(state),
            questions={
                name: {
                    "kind": a.kind,
                    "expectation_id": (
                        None if a.expectation is None else a.expectation.expectation_id.value
                    ),
                    "content": None if a.expectation is None else a.expectation.content,
                    "ground_id": a.ground_id,
                }
                for name, a in (asked or {}).items()
            },
            answers={
                name: {
                    "value": answer.value,
                    "probabilities": dict(answer.probabilities),
                    "confidence": answer.confidence,
                    "latency_ms": answer.latency_ms,
                    "source": answer.source.value,
                }
                for name, answer in (answers or {}).items()
            },
            transitions=[dict(t) for t in report.transitions],
            grounds=grounds or [],
        )


def _questions(
    self_name: str,
    *,
    pending: Sequence[Expectation],
    new: Sequence[Expectation],
    plan: GroundsPlan,
) -> tuple[dict[str, _Asked], dict[str, Question]]:
    # 質問の名前は連番にする。予期の ID を名前に使うと、答えを引くためだけに ID が
    # Jev に渡る (設計原則 1)。
    asked: dict[str, _Asked] = {}
    questions: dict[str, Question] = {}
    for index, expectation in enumerate(new):
        name = f"shape_{index}"
        asked[name] = _Asked("shape", expectation)
        questions[name] = ChoiceQuestion(
            instructions=(
                f"{self_name}がターン{expectation.formed_at_turn}に書いた予期"
                f"「{expectation.content}」"
                f"(いつ頃: {_due(expectation)}) は、どの形をしているか。"
                "当たったかどうかではなく、形だけを見る。"
            ),
            options={
                ShapeVerdict.SETTLEABLE.value: (
                    "清算できる予期。他の人や世界がこれからどうなるか、または"
                    f"{self_name}の行動の結果どうなるか (見つかる、手に入る、できる、"
                    "失敗する) を述べていて、このあと届く出来事で当たり外れが決まる"
                ),
                ShapeVerdict.TRUE_EITHER_WAY.value: (
                    "どう転んでも当たる形。「A か B のどちらか」「するか、しないか」"
                    "のように、どの結果でも当たりになる"
                ),
                ShapeVerdict.OWN_ACTION.value: (
                    f"{self_name}本人がこれから何をするか (〜へ向かう、〜を始める、"
                    "〜を決める。他の人と一緒にすることも含む) だけを述べていて、"
                    "その結果どうなるかを述べていない"
                ),
                ShapeVerdict.NOT_AN_EXPECTATION.value: (
                    "予期ではない。方針、ねらい、感想、願い、問いなど"
                ),
            },
        )
    for index, expectation in enumerate(pending):
        name = f"check_{index}"
        hearsay = f"hearsay_{index}"
        asked[name] = _Asked("check", expectation, hearsay_question=hearsay)
        questions[name] = ChoiceQuestion(
            instructions=(
                f"{self_name}がターン{expectation.formed_at_turn}に書いた予期"
                f"「{expectation.content}」(いつ頃: {_due(expectation)}) は、"
                "出来事の時系列に照らして当たったか。予期の中身だけを見て、"
                f"やり方の成否は問わない。主語の無い予期は{self_name}本人のこととして読む。"
                "「発言」の欄は、その人がそう言ったという事実で、言った中身が起きた"
                "ことの確かめにはならない。"
            ),
            options={
                CheckVerdict.HIT.value: "当たった。予期したことが起きた",
                CheckVerdict.MISS.value: (
                    "外れた。予期と違うことや予期に反する出来事が起きた、"
                    "またはいつ頃を過ぎても起きなかった"
                ),
                CheckVerdict.UNDETERMINED.value: (
                    "まだ分からない。決め手になる出来事がまだ届いていない。"
                    "予期の前提や条件がまだ起きていない場合も含む"
                ),
                CheckVerdict.NOT_AN_EXPECTATION.value: (
                    "予期になっていない。当たり外れを決められる形をしていない"
                ),
            },
        )
        asked[hearsay] = _Asked("hearsay", expectation)
        questions[hearsay] = NoulQuestion(
            instructions=(
                f"{self_name}の予期「{expectation.content}」について。時系列の中で、"
                "この予期が当たったと言える決め手は、誰かの発言の中身しかないか。"
            ),
            true_means=(
                "決め手は発言の中身しかない。誰かがそう言っただけで、"
                f"{self_name}がしたことや見聞きした出来事には、当たりを裏づけるものが無い"
            ),
            false_means=(
                f"{self_name}がしたことや見聞きした出来事に、当たりを裏づけるものがある。"
                "または予期が人の言動そのもの (誰かが何かを言う、来る) についてで、"
                "その言動が起きた。当たりと言える出来事が何も無い場合も含む"
            ),
        )
    for name, ground in plan.questions.items():
        asked[name] = _Asked("ground", ground.expectation, ground_id=ground.ground_id)
        questions[name] = ground_question(self_name, ground)
    asked[SCENE_QUESTION] = _Asked("scene")
    questions[SCENE_QUESTION] = NoulQuestion(
        instructions=f"いまのターンに、{self_name}のいる場面は前のターンから変わったか。",
        true_means="場所を移った、別の出来事に移った、時間が大きく飛んだなどで場面が変わった",
        false_means="同じ場所で同じ出来事が続いている",
    )
    return asked, questions


def _verdicts(
    asked: Mapping[str, _Asked], answers: Mapping[str, JudgmentResult]
) -> dict[str, ShapeVerdict | CheckVerdict | float]:
    """答えをすべて判定に直す。1 つでも使えなければ、どの予期にも渡さない。

    根拠の問いは確率のまま返す。根拠の答えだけが壊れたときも形を渡さないのは、
    形が判定済みなら根拠も判定済みという予期の決まりを保つため。
    """
    missing = sorted(set(asked) - set(answers))
    if missing:
        raise TypedJudgmentUnavailableException(
            f"expectation settlement answers missing for {missing}",
            error_code="TYPED_JUDGMENT_ANSWER_MISSING",
        )
    verdicts: dict[str, ShapeVerdict | CheckVerdict | float] = {}
    for name, a in asked.items():
        value = answers[name].value
        try:
            if a.kind == "shape":
                verdicts[name] = ShapeVerdict(value)
            elif a.kind == "check":
                verdicts[name] = CheckVerdict(value)
            elif a.kind in ("ground", "hearsay"):
                verdicts[name] = _probability(value)
            else:
                float(value)
        except (TypeError, ValueError) as exc:
            raise TypedJudgmentUnavailableException(
                f"expectation settlement answer {name}={value!r} is not usable",
                error_code="TYPED_JUDGMENT_ANSWER_INVALID",
                cause=exc,
            ) from exc
    return verdicts


def _probability(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"probability must be a number, got {value!r}")
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"probability must be in [0, 1], got {value!r}")
    return float(value)


def _state(
    self_name: str,
    *,
    now: int,
    pending: Sequence[Expectation],
    new: Sequence[Expectation],
    timeline: Sequence[_Turn],
) -> dict[str, Any]:
    # ターンも「ターン3」の文にする。整数をそのまま載せると、ID と同じ扱いで
    # 数として読まれうる (設計原則 1)。差の計算は Jev に任せない。
    return {
        "本人の名前": self_name,
        "いまのターン": f"ターン{now}",
        "清算待ちの予期": [_listed(e) for e in pending],
        "形を見る予期": [_listed(e) for e in new],
        "出来事の時系列": [
            {
                "ターン": f"ターン{t.turn}",
                "出来事": list(t.material.actions),
                "発言": list(t.material.speeches),
            }
            for t in timeline
        ],
    }


def _what_happened(
    timeline: Sequence[_Turn], *, since: int, until: int
) -> tuple[str, ...]:
    # 時系列は直近の数ターン分しか持たないので、書いたターンが落ちていれば残りだけになる。
    lines: list[str] = []
    for t in timeline:
        if since <= t.turn <= until:
            lines.extend(
                text
                for text in (*t.material.actions, *t.material.speeches)
                if text.strip()
            )
    return tuple(lines)


def _listed(expectation: Expectation) -> dict[str, str]:
    return {
        "書いたターン": f"ターン{expectation.formed_at_turn}",
        "いつ頃": _due(expectation),
        "確からしさ": LIKELIHOOD_LABELS[expectation.likelihood],
        "予期": expectation.content,
    }


def _due(expectation: Expectation) -> str:
    return expectation.due or "指定なし"


__all__ = [
    "SCENE_QUESTION",
    "SKIPPED_JUDGMENT_UNAVAILABLE",
    "SKIPPED_NOTHING_TO_JUDGE",
    "SKIPPED_SETTLEMENT_FAILED",
    "ExpectationSettlementService",
    "SettlementReport",
    "TurnMaterial",
]
