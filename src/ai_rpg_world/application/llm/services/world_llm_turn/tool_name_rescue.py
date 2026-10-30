"""存在しない tool 名への失敗文に、意図したと思われる tool を添える。

## 提案にとどめる

別の tool として実行はしない。引数の写し替えが要り、足りない引数の扱いが難しい
(#1413)。失敗は失敗のまま返し、「もしかして 'X' ですか?」の中身だけを選ぶ。

## 選び方は 2 段

1. 型付き判断が使えるなら、そのターンに送った tool のどれを意図したかを意味で問う
2. 判断が無い・「該当なし」なら、文字の類似度で近い名前を選ぶ

過去 89 run の 24 件は typo より発明された名前 (``say`` / ``gather``) に寄って
いて、先頭の単語が共通しないので 2 だけでは候補が出ない。

## 閾値は置かない

誤っても実行はせず、提案が外れるだけ。確率が低くても、「該当なし」以外を選べば
その tool を提案する (design_decisions #234)。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

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

logger = logging.getLogger(__name__)

#: 「送ったどの tool にも当たらない」を表す選択肢名。tool 名と衝突しない形にする。
NO_MATCH_OPTION = "__no_match__"

#: trace と呼び出し側の分岐に使う質問名。
QUESTION_NAME = "tool_name_rescue"

#: state では引数から外し、別の欄に置く。意図を示す材料として名前を付けて渡す。
_INTENT_FIELDS: tuple[str, ...] = ("inner_thought",)

_SUFFIX_RATIO_CUTOFF: float = 0.5
_SHORTENED_NAME_SCORE: float = 0.95

# PR-CC (Y_after_pr639_640 後続): 旧 ``spot_graph_`` prefix を廃止した後も、
# LLM は数 tick / 数 turn の間は「習慣」で ``spot_graph_pickup`` のような旧
# prefix 付き名を投げてくる可能性が高い。fuzzy match は「共通 prefix segment
# が 1 つ以上」を要求するため、旧 prefix 付き入力は valid (= bare 名) に対して
# 一切マッチしない。この差を吸収するため、requested の先頭が旧 prefix なら
# 剥がしたバージョンでも比較を試みる。
_LEGACY_TOOL_PREFIXES: tuple[str, ...] = ("spot_graph_",)


def suggest_closest_tool_name(requested: str, valid_tools: Iterable[str]) -> str | None:
    """typo っぽい tool 名から、最も近い valid tool 名 1 件を返す。

    共通 prefix segment が 1 つも無い候補は除外し、残った候補のうち suffix の
    類似度 (cutoff = ``_SUFFIX_RATIO_CUTOFF`` = 0.5) が最も高いものを返す。
    短縮形 (= requested の suffix が空) は ``_SHORTENED_NAME_SCORE`` 固定で
    常に救う。

    cutoff 0.5 は ``speech_speech → speech_speak`` の suffix 比較 ratio が
    0.545 になる事実から決定した境界値。これ未満にすると想像由来 typo
    (= ``gather`` / ``harvest``) の false positive が増える。

    候補が無ければ ``None``。「想像由来」(= ``gather`` / ``harvest`` のような
    独立した語) は本関数では救わず、``valid_tools`` 一覧の併記で agent に
    再選択させる設計。
    """
    if not isinstance(requested, str) or not requested:
        return None
    valid_list = [v for v in valid_tools if isinstance(v, str) and v]
    if not valid_list:
        return None

    # PR-CC 追加: 旧 prefix 剥がしを試す (bare 名との fuzzy 比較を可能にする)。
    # 「spot_graph_pickup → pickup_item」のような救済経路。
    # 元の requested と剥がした版の両方を候補にして、スコアが高い方を選ぶ。
    candidates_to_try: list[str] = [requested]
    for legacy in _LEGACY_TOOL_PREFIXES:
        if requested.startswith(legacy) and len(requested) > len(legacy):
            candidates_to_try.append(requested[len(legacy) :])
            break

    best: str | None = None
    best_score: float = 0.0
    for req_variant in candidates_to_try:
        variant_best, variant_score = _fuzzy_score_variant(req_variant, valid_list, SequenceMatcher)
        if variant_score > best_score:
            best_score = variant_score
            best = variant_best

    # strict `>` を使う: `harvest` vs `travel_to` が ratio=0.5 で false positive
    # にならないように、cutoff と等しい match は救わない。`speech_speak`
    # (= ratio 0.545) は通る。
    if best_score > _SUFFIX_RATIO_CUTOFF:
        return best
    return None


def _fuzzy_score_variant(requested: str, valid_list: list[str], sequence_matcher: Any) -> tuple[str | None, float]:
    """1 つの ``requested`` variant について、valid 側から最高スコアを持つ
    候補を返す。``suggest_closest_tool_name`` の内部ヘルパー。"""
    req_parts = requested.split("_")
    best: str | None = None
    best_score: float = 0.0
    for cand in valid_list:
        cand_parts = cand.split("_")
        common = 0
        for r, c in zip(req_parts, cand_parts):
            if r == c:
                common += 1
            else:
                break
        if common == 0:
            continue  # 全く異なるカテゴリ
        req_suffix = "_".join(req_parts[common:])
        cand_suffix = "_".join(cand_parts[common:])
        if not req_suffix and cand_suffix:
            # 短縮形 (e.g. spot_graph_pickup → spot_graph_pickup_item)
            score = _SHORTENED_NAME_SCORE
        elif not cand_suffix and req_suffix:
            # 逆短縮 (= candidate がより短い)。これは LLM が「サフィックス付
            # きの方を呼びたかった」と推定するには弱いので 0.0 扱い
            score = 0.0
        elif not req_suffix and not cand_suffix:
            # 完全一致 (= requested == cand。この経路は handler が見つかって
            # いるはずなので来ない、念のため)
            score = 1.0
        else:
            score = sequence_matcher(None, req_suffix, cand_suffix).ratio()
        if score > best_score:
            best_score = score
            best = cand
    return best, best_score


def build_unsupported_tool_message(*, requested: str, valid_tools: Iterable[str]) -> str:
    """UNSUPPORTED_TOOL 用のエラーメッセージを、文字の類似度による提案つきで組み立てる。"""
    valid_sorted = sorted(v for v in valid_tools if isinstance(v, str) and v)
    return format_unsupported_tool_message(
        requested=requested,
        valid_tools=valid_sorted,
        suggestion=suggest_closest_tool_name(requested, valid_sorted),
    )


def format_unsupported_tool_message(*, requested: str, valid_tools: Iterable[str], suggestion: str | None) -> str:
    """UNSUPPORTED_TOOL 用のエラーメッセージを組み立てる。

    含む情報:
    1. 呼ばれた名前
    2. 提案 (「もしかして 'X' ですか?」、候補がある時のみ)
    3. 使える tool の一覧 (提案が外れても選び直せるよう常に併記)
    """
    valid_sorted = sorted(v for v in valid_tools if isinstance(v, str) and v)
    head = f"未対応のツールです: {requested}"
    if suggestion:
        head += f"。もしかして '{suggestion}' ですか?"
    else:
        head += "。"
    tail = f" 現在使える tool: [{', '.join(valid_sorted)}]"
    return head + tail


@dataclass(frozen=True)
class ToolNameJudgment:
    """意図した tool を問うた結果。採らなかった判断と、得られなかった判断も残す。

    Attributes:
        chosen: 判断が選んだ tool。「該当なし」や判断が無いときは None
        probabilities: 選択肢ごとの確率
        confidence: モデルが返した confidence
        accepted: 判断の選んだ tool を提案にしたか
        fallback_reason: 類似度の提案に戻した理由。``no_match`` /
            ``unavailable``。採ったときは None
        unavailable_reason: 判断を得られなかったときのエラーコード
    """

    chosen: str | None
    probabilities: Mapping[str, float]
    confidence: float | None
    accepted: bool
    fallback_reason: str | None
    latency_ms: float | None = None
    source: str | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class ToolNameSuggestion:
    """失敗文に添える提案と、それをどう決めたか。

    Attributes:
        tool: 提案する tool。候補が無ければ None
        source: ``judgment`` / ``similarity``。提案が無ければ None
        judgment: 判断を問うたときの結果。問わなかったときは None
    """

    requested: str
    tool: str | None
    source: str | None
    options: tuple[str, ...] = field(default=())
    judgment: ToolNameJudgment | None = None

    def trace_payload(self) -> dict[str, Any] | None:
        """TYPED_JUDGMENT に残す値。判断を問うていなければ None。

        ``suggested`` と、同じ player の次の ``action`` の ``tool`` を突き合わせれば、
        提案どおりの tool が呼ばれたかを数えられる。
        """
        j = self.judgment
        if j is None:
            return None
        return {
            "requested": self.requested,
            "options": list(self.options),
            "chosen": j.chosen,
            "probabilities": dict(j.probabilities),
            "confidence": j.confidence,
            "accepted": j.accepted,
            "suggested": self.tool,
            "suggestion_source": self.source,
            "fallback_reason": j.fallback_reason,
            "latency_ms": j.latency_ms,
            "source": j.source,
            "unavailable_reason": j.unavailable_reason,
        }


class ToolNameRescue:
    """存在しない tool 名から、送った tool のどれを意図したかを意味で選ぶ。"""

    def __init__(self, *, port: ITypedJudgmentPort) -> None:
        self._resolver = SemanticResolver(
            backend=_ToolNameBackend(port),
            policy=_AcceptAnyChoice(),
        )

    def suggest(
        self,
        requested: str,
        *,
        offered: Mapping[str, str | None],
        arguments: Mapping[str, Any],
    ) -> ToolNameSuggestion:
        """提案を選ぶ。判断を採らなければ文字の類似度による提案に戻す。

        Args:
            requested: 呼ばれた名前
            offered: そのターンに送った tool 名 → 説明の 1 行目
            arguments: 呼び出しに付いていた引数
        """
        options = tuple(sorted(offered))
        similar = suggest_closest_tool_name(requested, options)
        if not requested.strip() or not options:
            return _by_similarity(requested, similar, options, judgment=None)
        try:
            result = self._resolver.resolve(
                value=requested,
                candidates=[Candidate(name, (offered[name] or "").strip() or name) for name in options],
                context=_state(requested, arguments, offered),
            )
        except BackendError as exc:
            # 静かに類似度へ戻さない。判断を得られなかったことを残す
            # (design_decisions #5)。
            logger.warning("tool name rescue unavailable: %s", exc)
            return self._unavailable(requested, similar, options, exc.code)
        except Exception:
            # 例外を外へ出すと、UNSUPPORTED_TOOL が汎用の失敗に変わり、tool の一覧と
            # 次 tick の起床が失われる。
            logger.exception("tool name rescue failed")
            return self._unavailable(requested, similar, options, "UNEXPECTED_ERROR")
        assert result.judgment is not None
        answer = result.judgment.evidence
        accepted = isinstance(result, Resolved)
        judgment = ToolNameJudgment(
            chosen=result.judgment.value,
            probabilities=dict(answer.probabilities),
            confidence=answer.confidence,
            accepted=accepted,
            fallback_reason=None if isinstance(result, Resolved) else result.reason,
            latency_ms=answer.latency_ms,
            source=answer.source.value,
        )
        if isinstance(result, Resolved):
            return ToolNameSuggestion(
                requested=requested,
                tool=result.value,
                source="judgment",
                options=options,
                judgment=judgment,
            )
        return _by_similarity(requested, similar, options, judgment=judgment)

    def _unavailable(
        self,
        requested: str,
        similar: str | None,
        options: tuple[str, ...],
        reason: str | None,
    ) -> ToolNameSuggestion:
        return _by_similarity(
            requested,
            similar,
            options,
            judgment=ToolNameJudgment(
                chosen=None,
                probabilities={},
                confidence=None,
                accepted=False,
                fallback_reason="unavailable",
                unavailable_reason=reason,
            ),
        )


def _by_similarity(
    requested: str,
    similar: str | None,
    options: tuple[str, ...],
    *,
    judgment: ToolNameJudgment | None,
) -> ToolNameSuggestion:
    return ToolNameSuggestion(
        requested=requested,
        tool=similar,
        source="similarity" if similar else None,
        options=options,
        judgment=judgment,
    )


class _ToolNameBackend:
    """既存ポートの通信・再試行・stub をライブラリの判断契約へ接続する。"""

    def __init__(self, port: ITypedJudgmentPort) -> None:
        self._port = port

    def judge(self, request: ResolutionRequest) -> Judgment[JudgmentResult]:
        options = {c.value: c.description for c in request.candidates}
        if NO_MATCH_OPTION in options:
            raise BackendError("tool name collides with the no-match option")
        question = ChoiceQuestion(
            instructions=(
                "存在しない tool 名 called_tool_name で呼び出した。この呼び出しで、"
                "いま使える手立てのうちどれをしようとしたか。どれにも当たらなければ "
                f"{NO_MATCH_OPTION} を選ぶ。"
            ),
            options={**options, NO_MATCH_OPTION: "いま使えるどの手立てとも対応しない"},
        )
        try:
            answers = self._port.judge(request.context, {QUESTION_NAME: question})
        except TypedJudgmentUnavailableException as exc:
            raise BackendError(str(exc), code=exc.error_code) from exc
        answer = answers.get(QUESTION_NAME)
        if answer is None:
            raise BackendError("tool name rescue answer missing", code="ANSWER_MISSING")
        chosen = str(answer.value)
        return Judgment(
            value=None if chosen == NO_MATCH_OPTION else chosen,
            evidence=answer,
            backend=answer.source.value,
            # 既存ポートはモデル名を公開しないため、推測して埋めない。
            model="",
            latency_ms=answer.latency_ms,
        )


class _AcceptAnyChoice:
    """「該当なし」は resolver が先に落とすので、ここに届いた選択はすべて採る。"""

    def assess(self, judgment: Judgment[JudgmentResult]) -> Assessment:
        return Assessment(reason="accepted", thresholds={})


def _state(
    requested: str,
    arguments: Mapping[str, Any],
    offered: Mapping[str, str | None],
) -> dict[str, Any]:
    """判断の材料。どの引数を書いたかは意図を強く示す (``say`` と ``content``)。

    整数の引数は入れない。発明された呼び出しでも ``item_id`` のような ID を
    書いてくることがあり、判断に整数 ID を渡さない (設計原則 1)。
    """
    state: dict[str, Any] = {
        "called_tool_name": requested,
        "arguments": {
            key: value
            for key, value in arguments.items()
            if key not in _INTENT_FIELDS and not (isinstance(value, int) and not isinstance(value, bool))
        },
        "available_tools": {name: offered[name] or name for name in sorted(offered)},
    }
    for key in _INTENT_FIELDS:
        text = arguments.get(key)
        if isinstance(text, str) and text.strip():
            state[key] = text.strip()
    return state
