"""発明された行動名を、対象の操作一覧から意味で選び直す (#1321)。

``_pick_action_name`` は表示を写したときの表記の崩れだけを救い、``gather`` のような発明された
名前は「その操作はありません」で失敗させていた。65 run で 111 件の主因である。
文字の類似度では ``gather`` を ``reap_wheat`` に安全に寄せられないので、意図的に
諦めていた。

意味で選べるなら寄せられる。確信が低ければ従来どおり失敗させる。

## 問わない場面

- 一覧に当たった名前 (表記の崩れの正規化を含む): 問う必要がない
- 候補集合が空: 行為者に操作をすべて伏せた物体 (design_decisions #46)。ここで
  問うと、伏せた操作の存在を確率として漏らしかねない

つまり **当たらなかったときだけ** 問う。

## 「該当なし」を必ず選択肢に入れる

入れないと、どれにも当たらない名前でも必ずどれかに寄る。世界に無い行為を
「一番近い操作」に化けさせない。

選択肢は対象が実際に持つ操作だけにする。世界に無い操作を作らない。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from semantic_resolver import (
    Assessment,
    BackendError,
    Candidate,
    Judgment,
    ResolutionRequest,
    Resolved,
    SemanticResolver,
)

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    TypedJudgmentUnavailableException,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
    from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
        ActionNameResolution,
    )

logger = logging.getLogger(__name__)

#: 「一覧のどれにも当たらない」を表す選択肢名。
#:
#: 操作名と衝突しない形にする。``none`` のような名前だと、世界に ``none``
#: という操作があるかのように読める。
NO_MATCH_OPTION = "__no_match__"

#: trace と呼び出し側の分岐に使う質問名。
QUESTION_NAME = "action_name_rescue"


@dataclass(frozen=True)
class ActionNameJudgment:
    """行動名の選び直しを問うた結果。採否と、採否を決めた値を対で持つ。

    採らなかった判断も残す。残さないと「問わなかった」と「問って採らなかった」
    が trace で同じに見え、閾値を動かす判断ができない。

    Attributes:
        chosen: 選ばれた操作名。``NO_MATCH_OPTION`` のときは None
        probability: 選ばれた選択肢の確率
        confidence: モデルが返した confidence
        min_confidence: 採用の閾値
        accepted: 置き換えたか
        latency_ms: 呼び出しにかかった時間
        source: 判断の出所 (``jev`` / ``stub``)
        unavailable_reason: 判断を得られなかったときの理由。得られたときは None
    """

    chosen: str | None
    probability: float | None
    confidence: float | None
    min_confidence: float
    accepted: bool
    latency_ms: float | None = None
    source: str | None = None
    unavailable_reason: str | None = None


class ActionNameRescue:
    """一覧に当たらなかった行動名を、意味で選び直す。"""

    def __init__(self, *, port: ITypedJudgmentPort, min_confidence: float) -> None:
        if not isinstance(min_confidence, (int, float)):
            raise TypeError("min_confidence must be a number")
        if not 0.0 < float(min_confidence) <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        self._resolver = SemanticResolver(
            backend=_ActionNameBackend(port),
            policy=_ActionNamePolicy(float(min_confidence)),
        )
        #: 公開するのは、閾値が profile から届いたかを外から確かめるため。
        self.min_confidence = float(min_confidence)

    def rescue(
        self,
        resolution: ActionNameResolution,
        *,
        target: ToolRuntimeTargetDto,
        inner_thought: str | None,
    ) -> ActionNameResolution:
        """当たらなかった名前だけを問い直し、確信があれば置き換えた結果を返す。

        置き換えないときは受け取った ``resolution`` をそのまま返す (判断を
        問うた場合は ``judgment`` だけを足す)。
        """
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
            ActionNameResolution,
            ActionNameSource,
        )

        if resolution.source is not ActionNameSource.UNRESOLVED:
            return resolution

        options = _offered_options(target)
        if not options:
            # 候補が無い状態は NOT_OFFERED として届くので通常はここへ来ない。
            return resolution

        # 空の入力は意味を判断する材料がない。ライブラリへ渡す前に残す。
        if not resolution.original.strip():
            return resolution
        state = _state(resolution.original, target, inner_thought, options)
        try:
            result = self._resolver.resolve(
                value=resolution.original,
                candidates=[Candidate(name, label or name) for name, label in options.items()],
                context=state,
            )
        except BackendError as exc:
            # 静かに従来経路へ戻さない。**判断を得られなかったこと**を残す。
            # 残さないと、OFF の run と全件 fallback の run が trace で同じに
            # 見える (design_decisions #5)。
            logger.warning("action name rescue unavailable: %s", exc)
            return ActionNameResolution(
                value=resolution.value,
                original=resolution.original,
                source=ActionNameSource.UNRESOLVED,
                judgment=ActionNameJudgment(
                    chosen=None,
                    probability=None,
                    confidence=None,
                    min_confidence=self.min_confidence,
                    accepted=False,
                    unavailable_reason=exc.code,
                ),
            )

        # 候補は空でないので、採否にかかわらず判断の証拠が返る。
        assert result.judgment is not None
        answer = result.judgment.evidence
        chosen = result.judgment.value
        probability = answer.probabilities.get(str(answer.value))
        accepted = isinstance(result, Resolved)
        judgment = ActionNameJudgment(
            chosen=chosen,
            probability=probability,
            confidence=answer.confidence,
            min_confidence=self.min_confidence,
            accepted=accepted,
            latency_ms=answer.latency_ms,
            source=answer.source.value,
        )
        if not isinstance(result, Resolved):
            return ActionNameResolution(
                value=resolution.value,
                original=resolution.original,
                source=ActionNameSource.UNRESOLVED,
                judgment=judgment,
            )
        return ActionNameResolution(
            value=result.value,
            original=resolution.original,
            source=ActionNameSource.JUDGMENT,
            judgment=judgment,
        )


class _ActionNameBackend:
    """既存ポートの通信・再試行・stub をライブラリの判断契約へ接続する。"""

    def __init__(self, port: ITypedJudgmentPort) -> None:
        self._port = port

    def judge(self, request: ResolutionRequest) -> Judgment[JudgmentResult]:
        options = {candidate.value: candidate.description for candidate in request.candidates}
        if NO_MATCH_OPTION in options:
            raise BackendError("action name collides with the no-match option")
        question = ChoiceQuestion(
            instructions=(
                "書かれた行動名 written_action_name は、対象が持つ操作の"
                "どれを意図しているか。どれにも当たらなければ "
                f"{NO_MATCH_OPTION} を選ぶ。"
            ),
            options={**options, NO_MATCH_OPTION: "一覧のどの操作とも対応しない"},
        )
        try:
            answers = self._port.judge(request.context, {QUESTION_NAME: question})
        except TypedJudgmentUnavailableException as exc:
            raise BackendError(str(exc), code=exc.error_code) from exc
        answer = answers.get(QUESTION_NAME)
        if answer is None:
            raise BackendError("action name rescue answer missing", code="ANSWER_MISSING")
        chosen = str(answer.value)
        return Judgment(
            value=None if chosen == NO_MATCH_OPTION else chosen,
            evidence=answer,
            backend=answer.source.value,
            # 既存ポートはモデル名を公開しないため、推測して埋めない。
            model="",
            latency_ms=answer.latency_ms,
        )


class _ActionNamePolicy:
    """確率と、省略可能な確信度について従来の採用基準を維持する。"""

    def __init__(self, minimum: float) -> None:
        self._minimum = minimum

    def assess(self, judgment: Judgment[JudgmentResult]) -> Assessment:
        answer = judgment.evidence
        probability = answer.probabilities.get(str(answer.value))
        accepted = (
            probability is not None
            and probability >= self._minimum
            and (answer.confidence is None or answer.confidence >= self._minimum)
        )
        return Assessment(
            reason="accepted" if accepted else "below_threshold",
            thresholds={"min_probability": self._minimum, "min_confidence": self._minimum},
        )


def _offered_options(target: ToolRuntimeTargetDto) -> dict[str, str | None]:
    """対象が持つ操作名 → 意味ラベル。ラベルの無い操作は None。

    候補は ``available_interactions`` だけにする。表示で「いまできない」に
    回った操作も残す — 解決できる候補集合は表示の都合で変えない
    (design_decisions #37)。
    """
    labels = dict(getattr(target, "interaction_labels", ()) or ())
    return {name: labels.get(name) for name in (getattr(target, "available_interactions", ()) or ())}


def _state(
    written: str,
    target: ToolRuntimeTargetDto,
    inner_thought: str | None,
    options: Mapping[str, str | None],
) -> dict[str, Any]:
    """判断の材料。**名前だけを入れ、整数 ID を入れない** (設計原則 1)。"""
    state: dict[str, Any] = {
        "written_action_name": written,
        "target": target.display_name,
        "available_interactions": {name: label for name, label in options.items() if label} or list(options),
    }
    thought = (inner_thought or "").strip()
    if thought:
        state["inner_thought"] = thought
    return state


__all__ = ["ActionNameJudgment", "ActionNameRescue", "NO_MATCH_OPTION", "QUESTION_NAME"]
