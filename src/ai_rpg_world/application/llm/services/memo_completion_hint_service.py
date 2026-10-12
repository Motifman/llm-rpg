"""Memo 完了 hint サービス (Issue #188 Phase 1c、#1322 で意味判定を追加)。

LLM が memo_done を呼ばずに memo を放置した場合の救済策。直近の action_summary /
result_summary と未完了 memo を比べ、達成した可能性があれば「もしかして memo を
完了しましたか？」という hint を result_summary に append する。

## 文字の重なりでは 2 方向に外れる

当初は memo と行動 / 結果の共通部分文字列の割合が 0.6 以上で hint を出していた。

- **言い換えられた memo を拾えない**: 「夕食の材料を集める」と書いて麦を刈り
  取っても、文字が重ならないので hint が出ない
- **失敗した行動でも誤検出する**: 「水を汲む」と書いて井戸で汲もうとし、桶が
  無くて汲めなかった場合も、文字が重なるので hint が出る (重なり 0.75)

Noul なら意味で判定できる (#1322)。判断を持たない run は従来の重なり判定で動く。

## 1 回の呼び出しにまとめる

未完了 memo ごとに問うが、リクエストは 1 回にする。質問ごとに割ると state を
送り直すので、Noul 3 問で input tokens が 2.3 倍になる (実測 630 → 1,476)。

## 変えない判断

- **自動完了しない**: 抽象的な memo 内容はコード状態にマップできない。memo_done
  を呼ぶかどうかは当人に委ねる (hint を見て判断する)
- **hint 文の形を変えない**: `[hint] memo「...」(id: ...)` と「memo_done で記録
  してください」は既存 run と同じ。hint 件数と hint 後の memo_done 率を同じ形で
  比較できるようにする

ただし**数の呼び名は変える**。重なりの割合と較正済みの確率は別物なので、判断
由来の数を「類似度」と呼ばない。比較に使うのは hint の件数と `MEMO_HINT` の
記録で、この語ではない。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry

DEFAULT_SIMILARITY_THRESHOLD = 0.6
"""重なり判定で hint を出す閾値 (0.0-1.0)。

ここでの「類似度」は **memo 側に対する被覆率**: SequenceMatcher の
get_matching_blocks で memo と haystack (action_summary + result_summary) の
共通部分文字列長を合計し、len(memo) で割った値。memo が haystack に
ほぼ含まれていれば 1.0 に近い。SequenceMatcher.ratio() を使わない理由:
ratio() は両側の総長で割るため、action_summary が長いと memo が完全に
含まれていても低い値になり、hint が出にくくなる。

0.6 前後の根拠: memo の 6 割以上が action / result に再出現していれば
「達成した」とみなすのが経験的に妥当。
"""

DEFAULT_MIN_PROBABILITY = 0.7
"""意味判定で hint を出す確率の閾値 (#1322)。

**実測前の暫定値である。** 低くすると、語の重なりで誤検出していたのと同じ形で
無関係な行動に hint を出す。人手ラベルで較正して決め直す (#1319)。
"""

#: hint の数が何を指すか。
SOURCE_OVERLAP = "overlap"
SOURCE_JUDGMENT = "judgment"

#: trace と呼び出し側の分岐に使う質問名。
QUESTION_NAME = "memo_completed"


def _memo_coverage_ratio(memo_content: str, haystack: str) -> float:
    """memo の何割が haystack 内に再出現しているかを返す (0.0-1.0)。

    SequenceMatcher.get_matching_blocks() で memo と haystack の共通部分
    文字列長を合計し ``len(memo)`` で割る。memo がほぼ haystack に含まれて
    いれば 1.0 に近い。SequenceMatcher.ratio() (両側の総長で割る) と違って
    haystack が長くてもスコアが薄まらないため、長い action_summary でも
    memo 達成を検出できる。
    """
    if not memo_content:
        return 0.0
    matcher = SequenceMatcher(None, memo_content, haystack, autojunk=False)
    matched_chars = sum(block.size for block in matcher.get_matching_blocks())
    return matched_chars / len(memo_content)


@dataclass(frozen=True)
class PendingTodo:
    """メモ帳のやること 1 件 (#1628)。判定は ``MemoEntry`` と同じく ``id`` と ``content`` を見る。"""

    id: str
    content: str
    handle: str


@dataclass(frozen=True)
class MemoCompletionHint:
    """検出された hint。result_summary への append 用テキストも保持。

    Attributes:
        memo: 達成した可能性がある memo
        similarity: hint に載せる数。``source`` が何の数かを決める
        source: ``overlap`` なら文字の重なりの割合、``judgment`` なら確率
    """

    memo: MemoEntry | PendingTodo
    similarity: float
    source: str = SOURCE_OVERLAP

    def to_hint_text(self) -> str:
        """LLM に見せる hint 文を返す。"""
        from ai_rpg_world.application.llm.services.memo_id_display import (
            short_memo_id,
        )

        # 重なりの割合と確率を同じ語で呼ばない。当人に見せる文なので、数の
        # 意味が違うことは言葉で分かる必要がある。
        measure = "確度" if self.source == SOURCE_JUDGMENT else "類似度"
        if isinstance(self.memo, PendingTodo):
            # 自動では消さない。済んだかを決めるのは本人。
            return (
                f"\n\n[hint] やること「{self.memo.content}」({self.memo.handle}) "
                f"は済んだかもしれません ({measure} {self.similarity:.2f})。"
                "済んだなら memo の remove で消してください。"
            )
        return (
            f"\n\n[hint] memo「{self.memo.content}」(id: {short_memo_id(self.memo.id)}) "
            f"を達成した可能性があります ({measure} {self.similarity:.2f})。"
            "完了したなら memo_done で記録してください。"
        )


@dataclass(frozen=True)
class MemoCompletionJudgment:
    """memo 1 件について「果たされたか」を問うた結果。

    採らなかった判断も残す。残さないと「問わなかった」と「問って採らなかった」が
    trace で同じに見え、閾値を動かす判断ができない。
    """

    memo_id: str
    memo_content: str
    probability: float
    min_probability: float
    accepted: bool
    latency_ms: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class MemoHintDetection:
    """1 回の検出で起きたこと。

    Attributes:
        hint: 出す hint。無ければ None
        judgments: 問うた memo ごとの判断。問わなかったときは空
        unavailable_reason: 判断を得られず重なり判定へ縮退した理由。
            **ポートを持たない run では None** — 縮退ではないので区別する
    """

    hint: MemoCompletionHint | None
    judgments: tuple[MemoCompletionJudgment, ...] = ()
    unavailable_reason: str | None = None


class MemoCompletionHintService:
    """action_result への完了示唆 hint を生成する。

    使い方:
        service = MemoCompletionHintService(memo_store)
        detection = service.detect(being_id, action_summary, result_summary)

    detect は副作用なし: memo は完了させない。
    """

    def __init__(
        self,
        memo_store: MemoRepository | None = None,
        *,
        pending_todos: Callable[[BeingId], Sequence[PendingTodo]] | None = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        judgment_port: ITypedJudgmentPort | None = None,
        min_probability: float = DEFAULT_MIN_PROBABILITY,
    ) -> None:
        if (memo_store is None) == (pending_todos is None):
            raise TypeError("exactly one of memo_store or pending_todos is required")
        if memo_store is not None and not isinstance(memo_store, MemoRepository):
            raise TypeError("memo_store must be MemoRepository")
        if not isinstance(similarity_threshold, (int, float)):
            raise TypeError("similarity_threshold must be a number")
        if not (0.0 <= float(similarity_threshold) <= 1.0):
            raise ValueError("similarity_threshold must be in [0.0, 1.0]")
        if not isinstance(min_probability, (int, float)):
            raise TypeError("min_probability must be a number")
        if not 0.0 < float(min_probability) <= 1.0:
            raise ValueError("min_probability must be in (0, 1]")
        self._memo_store = memo_store
        self._pending_todos = pending_todos
        self._threshold = float(similarity_threshold)
        #: 公開するのは、配線が組まれたかを外から確かめられるようにするため。
        self.judgment_port = judgment_port
        self.min_probability = float(min_probability)

    def detect(
        self,
        being_id: BeingId,
        action_summary: str,
        result_summary: str,
    ) -> MemoHintDetection:
        """未完了 memo のうち、達成した可能性が最も高い 1 件の hint を返す。"""
        pending: Sequence[MemoEntry | PendingTodo] = (
            self._memo_store.list_uncompleted_by_being(being_id)
            if self._memo_store is not None
            else self._pending_todos(being_id)  # type: ignore[misc]
        )
        memos = [memo for memo in pending if (memo.content or "").strip()]
        haystack = f"{action_summary}\n{result_summary}".strip()
        if not memos or not haystack:
            # 判断の材料が無い。空の問い合わせに課金しない。
            return MemoHintDetection(hint=None)

        if self.judgment_port is None:
            return MemoHintDetection(hint=self._by_overlap(memos, haystack))

        try:
            return self._by_judgment(memos, action_summary, result_summary)
        except TypedJudgmentUnavailableException as exc:
            # 従来の重なり判定へ縮退する。ただし**縮退したことを残す**。
            # 残さないと、hint が減った run を見て「意味判定が厳しすぎる」と
            # 誤読する (design_decisions #5)。
            return MemoHintDetection(
                hint=self._by_overlap(memos, haystack),
                unavailable_reason=getattr(exc, "error_code", "UNAVAILABLE"),
            )

    def _by_overlap(
        self, memos: list[MemoEntry | PendingTodo], haystack: str
    ) -> MemoCompletionHint | None:
        best: MemoCompletionHint | None = None
        for memo in memos:
            ratio = _memo_coverage_ratio((memo.content or "").strip(), haystack)
            if ratio < self._threshold:
                continue
            if best is None or ratio > best.similarity:
                best = MemoCompletionHint(
                    memo=memo, similarity=ratio, source=SOURCE_OVERLAP
                )
        return best

    def _by_judgment(
        self,
        memos: list[MemoEntry | PendingTodo],
        action_summary: str,
        result_summary: str,
    ) -> MemoHintDetection:
        assert self.judgment_port is not None
        # 質問のキーは連番にする。memo の内部 ID をキーにすると、答えを引く
        # ためだけに ID が state 側の語彙へ混ざりやすい (設計原則 1)。
        by_key: dict[str, MemoEntry | PendingTodo] = {
            f"{QUESTION_NAME}_{index}": memo for index, memo in enumerate(memos)
        }
        questions = {
            key: NoulQuestion(
                instructions=(
                    f"この行動と結果で、memo「{(memo.content or '').strip()}」の"
                    "意図は果たされたか。"
                ),
                true_means="果たされた",
                false_means="まだ果たされていない",
            )
            for key, memo in by_key.items()
        }
        answers = self.judgment_port.judge(
            _state(action_summary, result_summary), questions
        )

        judgments: list[MemoCompletionJudgment] = []
        best: MemoCompletionHint | None = None
        for key, memo in by_key.items():
            answer = answers.get(key)
            if answer is None:
                # ポートの契約違反。欠けを「果たされていない」に読み替えない。
                raise TypedJudgmentUnavailableException(
                    f"memo completion answer missing for {key!r}",
                    error_code="TYPED_JUDGMENT_ANSWER_MISSING",
                )
            probability = float(answer.value)
            accepted = probability >= self.min_probability
            judgments.append(
                MemoCompletionJudgment(
                    memo_id=memo.id,
                    memo_content=(memo.content or "").strip(),
                    probability=probability,
                    min_probability=self.min_probability,
                    accepted=accepted,
                    latency_ms=answer.latency_ms,
                    source=answer.source.value,
                )
            )
            if accepted and (best is None or probability > best.similarity):
                best = MemoCompletionHint(
                    memo=memo, similarity=probability, source=SOURCE_JUDGMENT
                )
        return MemoHintDetection(hint=best, judgments=tuple(judgments))

    def augment_result_summary(
        self,
        being_id: BeingId,
        action_summary: str,
        result_summary: str,
    ) -> str:
        """result_summary に hint を append したものを返す。hint なしならそのまま。"""
        hint = self.detect(being_id, action_summary, result_summary).hint
        if hint is None:
            return result_summary
        return result_summary + hint.to_hint_text()


def _state(action_summary: str, result_summary: str) -> Mapping[str, Any]:
    """判断の材料。全 memo の質問が同じ state を見る。

    memo 本文は質問側に入れる。state に入れるのは行動と結果で、**memo の内部
    ID は入れない** (設計原則 1)。
    """
    return {"action": action_summary, "result": result_summary}


__all__ = [
    "DEFAULT_MIN_PROBABILITY",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "MemoCompletionHint",
    "MemoCompletionHintService",
    "MemoCompletionJudgment",
    "MemoHintDetection",
    "PendingTodo",
    "QUESTION_NAME",
    "SOURCE_JUDGMENT",
    "SOURCE_OVERLAP",
]
