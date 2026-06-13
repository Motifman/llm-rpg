"""Memo 完了 hint サービス (Issue #188 Phase 1c)。

LLM が memo_done を呼ばずに memo を放置した場合の救済策。
直近の action_summary / result_summary と未完了 memo の content を
``difflib.SequenceMatcher`` で比較し、類似度が閾値以上なら
「もしかして memo を完了しましたか？」という hint を result_summary に append する。

設計判断:
- ハード自動完了は採用しない: 抽象 memo 内容はコード状態にマップできない
- LLM が memo_done を呼ぶか無視するかは LLM 自身に委ねる (hint を見て判断)
- difflib は標準ライブラリで純 Python・依存ゼロ。100 文字 × memo 数件なら毎ターン
  実行しても無視できる速度 (~数 ms)
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


DEFAULT_SIMILARITY_THRESHOLD = 0.6
"""hint を出す類似度の閾値 (0.0-1.0)。

ここでの「類似度」は **memo 側に対する被覆率**: SequenceMatcher の
get_matching_blocks で memo と haystack (action_summary + result_summary) の
共通部分文字列長を合計し、len(memo) で割った値。memo が haystack に
ほぼ含まれていれば 1.0 に近い。SequenceMatcher.ratio() を使わない理由:
ratio() は両側の総長で割るため、action_summary が長いと memo が完全に
含まれていても低い値になり、hint が出にくくなる。

0.6 前後の根拠: memo の 6 割以上が action / result に再出現していれば
「達成した」とみなすのが経験的に妥当。
"""


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
class MemoCompletionHint:
    """検出された hint。result_summary への append 用テキストも保持。"""

    memo: MemoEntry
    similarity: float

    def to_hint_text(self) -> str:
        """LLM に見せる hint 文を返す。"""
        from ai_rpg_world.application.llm.services.memo_id_display import (
            short_memo_id,
        )
        return (
            f"\n\n[hint] memo「{self.memo.content}」(id: {short_memo_id(self.memo.id)}) "
            f"を達成した可能性があります (類似度 {self.similarity:.2f})。"
            "完了したなら memo_done で記録してください。"
        )


class MemoCompletionHintService:
    """action_result への完了示唆 hint を生成する。

    使い方:
        service = MemoCompletionHintService(memo_store)
        augmented = service.augment_result_summary(player_id, action_summary, result_summary)

    augment_result_summary は副作用なし: memo は完了させない。
    """

    def __init__(
        self,
        memo_store: MemoRepository,
        *,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        being_attachment_resolver: Optional["BeingAttachmentResolver"] = None,
        default_world_id: Optional["WorldId"] = None,
    ) -> None:
        if not isinstance(memo_store, MemoRepository):
            raise TypeError("memo_store must be MemoRepository")
        if not isinstance(similarity_threshold, (int, float)):
            raise TypeError("similarity_threshold must be a number")
        if not (0.0 <= float(similarity_threshold) <= 1.0):
            raise ValueError("similarity_threshold must be in [0.0, 1.0]")
        # Phase 3 Step 3a-2: Resolver + WorldId 注入時のみ being_id 経路。
        # 詳細は memo_executor の同様 dual-path コメント参照。
        from ai_rpg_world.domain.being.service.being_attachment_resolver import (
            BeingAttachmentResolver as _BAR,
        )
        from ai_rpg_world.domain.world.value_object.world_id import (
            WorldId as _WI,
        )
        if being_attachment_resolver is not None and not isinstance(
            being_attachment_resolver, _BAR
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if default_world_id is not None and not isinstance(default_world_id, _WI):
            raise TypeError("default_world_id must be WorldId")
        self._memo_store = memo_store
        self._threshold = float(similarity_threshold)
        self._resolver = being_attachment_resolver
        self._default_world_id = default_world_id

    def _list_uncompleted(self, player_id: PlayerId):
        """dual-path helper: Resolver + WorldId が揃えば新 API、なければ旧。"""
        if self._resolver is not None and self._default_world_id is not None:
            being_id = self._resolver.resolve_being_id(
                self._default_world_id, player_id
            )
            if being_id is not None:
                return self._memo_store.list_uncompleted_by_being(being_id)
        return self._memo_store.list_uncompleted(player_id)

    def detect(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
    ) -> Optional[MemoCompletionHint]:
        """最も類似度の高い未完了 memo の hint を返す。閾値未満は None。"""
        memos = self._list_uncompleted(player_id)
        if not memos:
            return None
        haystack = f"{action_summary}\n{result_summary}".strip()
        if not haystack:
            return None

        best: Optional[MemoCompletionHint] = None
        for memo in memos:
            content = (memo.content or "").strip()
            if not content:
                continue
            ratio = _memo_coverage_ratio(content, haystack)
            if ratio < self._threshold:
                continue
            if best is None or ratio > best.similarity:
                best = MemoCompletionHint(memo=memo, similarity=ratio)
        return best

    def augment_result_summary(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
    ) -> str:
        """result_summary に hint を append したものを返す。hint なしならそのまま。"""
        hint = self.detect(player_id, action_summary, result_summary)
        if hint is None:
            return result_summary
        return result_summary + hint.to_hint_text()


__all__ = [
    "DEFAULT_SIMILARITY_THRESHOLD",
    "MemoCompletionHint",
    "MemoCompletionHintService",
]
