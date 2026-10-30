"""言い直しや往復のような意味上の繰り返しを、型付き判断に問う検出器 (#1412)。

ループ警告の完全一致の検出は ``(tool 名, 引数の fingerprint)`` が揃わないと数えない。
言い直した同じ依頼、呼び名を変えた同じ失敗、2 つの行動の往復は、ルールでは
同じと判定できない。直近 K 件の行動と結果を材料に「手段を変えずに同じことを
試し続けているか」を 1 回だけ問う。

## 件数はコードが持つ

K と「何件並んだか」はこの検出器が数える。判断には数えさせない (算術は苦手だと
公表されている)。

## 本人の目的を材料に入れない

state は行為者の名前と、直近の行動の要約と結果だけ。内心や目的を足すと、判断が
LLM のターンを先取りする 2 つ目のエージェントになる (design_decisions #222)。

## 発火は控えめに

警告を足しすぎると待機へ押す可能性がある。閾値は高めに置き、signal を出したら
窓を空にして、新しい行動が K 件溜まるまで問わない。完全一致の検出が発火した
ときも窓を空にする。空にしないと、完全一致の警告の次のターンに同じ繰り返しへ
もう 1 件警告が届く (完全一致は閾値の倍数で、こちらは窓がそろった時点で発火し、
ずれる)。
"""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.loop_guard_detectors import (
    RecordedAction,
    SemanticRepeat,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

QUESTION_NAME = "semantic_repeat"

_RESULT_MAX_CHARS = 200


@dataclass(frozen=True)
class RecentAction:
    """窓に入る 1 件。判断に渡す形そのまま。"""

    action: str
    result: str
    succeeded: bool | None

    def as_state(self) -> dict[str, Any]:
        return {"action": self.action, "result": self.result, "succeeded": self.succeeded}


def _summarize(action: RecordedAction) -> str:
    # 要約は評価 (scripts/jev_semantic_repeat_demo.py) と同じ形にする。fingerprint は
    # 内心を除いた引数そのものなので、発言の内容も対象名もここから戻せる。
    try:
        arguments = json.loads(action.fingerprint)
    except (TypeError, ValueError):
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return format_action_summary_for_display(action.tool_name, arguments)


def build_state(actor: str, actions: Sequence[RecentAction]) -> dict[str, Any]:
    return {"actor": actor, "recent_actions": [a.as_state() for a in actions]}


def build_question(actor: str) -> NoulQuestion:
    return NoulQuestion(
        instructions=(
            f"{actor}は、直近のこれらの行動で、手段を変えずに同じことを試し続けているか。行動は古い順に並んでいる。"
        ),
        true_means=(
            "言い回し、呼び名、操作の名前が違っても、同じ相手や同じ対象に向けた同じ"
            "試みを繰り返していて、結果が同じまま変わっていない。同じ理由で拒否され"
            "続けている場合や、2 つの行動を行き来しているだけで状況が進んでいない場合も含む"
        ),
        false_means=("行動ごとに対象、相手、手段のどれかが変わっている。または前の結果を受けて次の段階へ進んでいる"),
    )


class SemanticRepeatDetector:
    """player ごとに直近 K 件の行動を持ち、K 件そろったら 1 回だけ問う。"""

    def __init__(
        self,
        judgment_port: ITypedJudgmentPort,
        *,
        player_name_resolver: Callable[[PlayerId], str],
        window_size: int,
        threshold: float,
        trace_recorder_provider: Callable[[], Any] | None = None,
    ) -> None:
        if not isinstance(judgment_port, ITypedJudgmentPort):
            raise TypeError("judgment_port must be ITypedJudgmentPort")
        if not isinstance(window_size, int) or window_size < 2:
            raise ValueError("window_size must be int >= 2")
        if not 0.0 < float(threshold) <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        self.judgment_port = judgment_port
        self.window_size = window_size
        self.threshold = float(threshold)
        self._player_name = player_name_resolver
        self._trace_recorder_provider = trace_recorder_provider
        self._windows: dict[int, deque[RecentAction]] = {}

    def observe(self, action: RecordedAction, *, exact_match_fired: bool = False) -> SemanticRepeat | None:
        """行動を 1 件積み、窓が K 件そろっていれば問う。1 回の呼び出しで問うのは最大 1 回。

        ``exact_match_fired`` は同じ行動で完全一致の検出が発火したか。trace に
        残して、2 つの検出の重なりを後から読めるようにする。発火していれば、
        この行動を最後に窓を空にする。警告を 1 件にまとめるのは警告の出し口。
        """
        key = int(action.player_key)
        window = self._windows.setdefault(key, deque(maxlen=self.window_size))
        window.append(
            RecentAction(
                _summarize(action),
                (action.result_summary or "")[:_RESULT_MAX_CHARS],
                action.success,
            )
        )
        if len(window) < self.window_size:
            if exact_match_fired:
                window.clear()
            return None

        actions = tuple(window)
        actor = self._player_name(PlayerId(key))
        probability: float | None = None
        latency_ms: float | None = None
        source: str | None = None
        unavailable_reason: str | None = None
        try:
            answer = self.judgment_port.judge(build_state(actor, actions), {QUESTION_NAME: build_question(actor)})[
                QUESTION_NAME
            ]
            probability = float(answer.value)
            latency_ms = answer.latency_ms
            source = answer.source.value
        except TypedJudgmentUnavailableException as exc:
            unavailable_reason = getattr(exc, "error_code", None) or "UNAVAILABLE"
        except KeyError:
            unavailable_reason = "TYPED_JUDGMENT_ANSWER_MISSING"
        except Exception:
            # ここから例外が漏れると、同じ行動で集めた完全一致の警告まで出なくなる。
            logger.exception("semantic repeat judgment failed")
            probability = None
            unavailable_reason = "UNEXPECTED_ERROR"

        accepted = probability is not None and probability >= self.threshold
        self._record(
            tick=action.tick,
            player_id=key,
            actions=actions,
            probability=probability,
            accepted=accepted,
            exact_match_fired=exact_match_fired,
            latency_ms=latency_ms,
            source=source,
            unavailable_reason=unavailable_reason,
        )
        if exact_match_fired:
            window.clear()
        if probability is None or not accepted:
            return None
        window.clear()
        return SemanticRepeat(
            tool_name=action.tool_name,
            fingerprint=action.fingerprint,
            count=len(actions),
            probability=probability,
            tick=action.tick,
        )

    def _record(
        self,
        *,
        tick: int | None,
        player_id: int,
        actions: tuple[RecentAction, ...],
        probability: float | None,
        accepted: bool,
        exact_match_fired: bool,
        latency_ms: float | None,
        source: str | None,
        unavailable_reason: str | None,
    ) -> None:
        provider = self._trace_recorder_provider
        recorder = provider() if provider is not None else None
        if recorder is None:
            return
        try:
            recorder.record(
                TraceEventKind.TYPED_JUDGMENT,
                tick=tick,
                player_id=player_id,
                question=QUESTION_NAME,
                window=[a.as_state() for a in actions],
                probability=round(probability, 4) if probability is not None else None,
                threshold=self.threshold,
                accepted=accepted,
                exact_match_fired=exact_match_fired,
                latency_ms=latency_ms,
                source=source,
                unavailable_reason=unavailable_reason,
            )
        except Exception:
            logger.exception("trace_recorder.record(semantic_repeat) failed")


__all__ = [
    "QUESTION_NAME",
    "RecentAction",
    "SemanticRepeatDetector",
    "build_question",
    "build_state",
]
