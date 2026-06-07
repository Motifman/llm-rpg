"""コンテキストフォーマット戦略 (escape_game format に統一)。"""

import logging
import os
from typing import Mapping, Optional

from ai_rpg_world.application.llm.contracts.interfaces import IContextFormatStrategy


# 順序ポリシー識別子。実験で A/B 比較できるよう constructor で切替可能。
# 詳細根拠は docs/memory_system/short_term_memory_design.md §5。
SECTION_ORDER_STABLE_TO_VOLATILE = "stable_to_volatile"
SECTION_ORDER_LEGACY = "legacy"

_VALID_SECTION_ORDERS = frozenset({
    SECTION_ORDER_STABLE_TO_VOLATILE,
    SECTION_ORDER_LEGACY,
})

# 実験スクリプトから A/B 切替するための env var 名。
# 既存の他の knob (EPISODIC_PROMOTION_FORCE_FULL_SCAN, SUBJECTIVE_EPISODE_DB_PATH
# 等) と同じ env-var パターンに揃える。
ENV_PROMPT_SECTION_ORDER = "PROMPT_SECTION_ORDER"


_logger = logging.getLogger(__name__)


class SectionBasedContextFormatStrategy(IContextFormatStrategy):
    """``【...】`` 見出し形式でコンテキストを組み立てる戦略。

    Issue #356 後続 (Phase 0): prefix cache 効率と Lost-in-the-middle 緩和を
    目的に section の並び順を見直した。default は ``stable_to_volatile`` で、
    更新頻度の低い section を上に、毎ターン変動する section を末尾近くに
    置く。A/B 検証のため ``legacy`` 順序も残してある。

    詳細根拠は ``docs/memory_system/short_term_memory_design.md`` §5。

    ## stable_to_volatile (default, Phase 0 以降)

    1. **【現在の目的】** — objective_text (scenario 固定の目標文)
    2. **【進行中のメモ】** — active_memos_text (memo 操作時のみ変動)
    3. **【所持・判明した物証】** — inventory_text (mid-volatile)
    4. **【関連する記憶】** — relevant_memories_text (mid-volatile)
    5. **【直近の出来事】** — recent_events_text (sliding window 由来の volatile)
    6. **【現在地と周囲】** — current_state_text (毎ターン更新の最 volatile / 必須)

    意図: 「現在地と周囲」を末尾に置くことで:
      - prefix cache は ① 〜 ⑤ までで止まり、安定 prefix を最大化
      - LLM の attention は末尾が強い (Lost in the Middle, Liu et al. 2023) ので
        「今ここ」情報の重みが上がり、tool 選択精度が高まる

    ## legacy (旧順序、A/B 用)

    1. **【現在の目的】**
    2. **【現在地と周囲】**
    3. **【進行中のメモ】**
    4. **【直近の出来事】**
    5. **【関連する記憶】**
    6. **【所持・判明した物証】**

    Issue #227 chore β で導入された順序。「現在地」を上部に置いていたため
    prefix cache が user content 序盤で切れる課題があった。
    """

    def __init__(self, section_order: str = SECTION_ORDER_STABLE_TO_VOLATILE) -> None:
        if section_order not in _VALID_SECTION_ORDERS:
            raise ValueError(
                f"section_order must be one of {sorted(_VALID_SECTION_ORDERS)}; "
                f"got {section_order!r}"
            )
        self._section_order = section_order

    @property
    def section_order(self) -> str:
        """現在の section 順序ポリシー識別子。"""
        return self._section_order

    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        relevant_memories_text: str = "",
        active_memos_text: str = "",
        objective_text: str = "",
        inventory_text: str = "",
        learned_text: str = "",
        mid_summary_text: str = "",
        long_summary_text: str = "",
    ) -> str:
        for name, value in (
            ("current_state_text", current_state_text),
            ("recent_events_text", recent_events_text),
            ("relevant_memories_text", relevant_memories_text),
            ("active_memos_text", active_memos_text),
            ("objective_text", objective_text),
            ("inventory_text", inventory_text),
            ("learned_text", learned_text),
            ("mid_summary_text", mid_summary_text),
            ("long_summary_text", long_summary_text),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{name} must be str")

        if self._section_order == SECTION_ORDER_LEGACY:
            return _format_legacy(
                current_state_text=current_state_text,
                recent_events_text=recent_events_text,
                relevant_memories_text=relevant_memories_text,
                active_memos_text=active_memos_text,
                objective_text=objective_text,
                inventory_text=inventory_text,
                learned_text=learned_text,
                mid_summary_text=mid_summary_text,
                long_summary_text=long_summary_text,
            )
        return _format_stable_to_volatile(
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            relevant_memories_text=relevant_memories_text,
            active_memos_text=active_memos_text,
            objective_text=objective_text,
            inventory_text=inventory_text,
            learned_text=learned_text,
            mid_summary_text=mid_summary_text,
            long_summary_text=long_summary_text,
        )


# ──────────────────────────────────────────────────────────────────
# env var 由来の factory。実験スクリプトから A/B 切替する用途。
# ──────────────────────────────────────────────────────────────────


def resolve_section_order_from_env(
    env: Optional[Mapping[str, str]] = None,
) -> str:
    """``PROMPT_SECTION_ORDER`` env var から section 順序を解決する。

    実験スクリプト経由で A/B 検証する用途。``env`` を渡せばその dict を見る
    (テスト用)、None なら ``os.environ``。

    - 値が未設定・空文字なら default の ``stable_to_volatile`` を返す
    - 値が未知の文字列なら ``ValueError`` (silent fallback 防止 / PR #433 経緯)

    Raises:
        ValueError: 未知の文字列のとき
    """
    source = env if env is not None else os.environ
    raw = (source.get(ENV_PROMPT_SECTION_ORDER) or "").strip()
    if not raw:
        return SECTION_ORDER_STABLE_TO_VOLATILE
    if raw not in _VALID_SECTION_ORDERS:
        raise ValueError(
            f"{ENV_PROMPT_SECTION_ORDER}={raw!r} is not recognized. "
            f"valid: {sorted(_VALID_SECTION_ORDERS)}"
        )
    return raw


def build_section_format_strategy_from_env(
    env: Optional[Mapping[str, str]] = None,
) -> SectionBasedContextFormatStrategy:
    """``PROMPT_SECTION_ORDER`` env var を見て strategy を構築するファクトリ。

    wiring から呼ぶ。env 未設定なら default の stable_to_volatile で動く。
    """
    order = resolve_section_order_from_env(env=env)
    _logger.info("SectionBasedContextFormatStrategy section_order=%s", order)
    return SectionBasedContextFormatStrategy(section_order=order)


# ──────────────────────────────────────────────────────────────────
# 順序ごとの実装。順序ポリシーは差し替え可能だが、各 section の
# 文言・空時の placeholder・前置きは共通なのでヘルパに切り出す。
# ──────────────────────────────────────────────────────────────────


_PLACEHOLDER_CURRENT_STATE = "（情報なし）"
_PLACEHOLDER_RECENT_EVENTS = "（なし）"
_RECENT_EVENTS_PREAMBLE = "観測（世界から届いた事象）と、あなた自身の行動の結果が時系列に並びます。"


def _emit_objective(sections: list, objective_text: str) -> None:
    if objective_text.strip():
        sections.extend([
            "【現在の目的】",
            objective_text.strip(),
            "",
        ])


def _emit_current_state(sections: list, current_state_text: str) -> None:
    sections.extend([
        "【現在地と周囲】",
        current_state_text.strip() or _PLACEHOLDER_CURRENT_STATE,
    ])


def _emit_active_memos(sections: list, active_memos_text: str) -> None:
    if active_memos_text.strip():
        sections.extend([
            "",
            "【進行中のメモ】",
            active_memos_text.strip(),
        ])


def _emit_recent_events(sections: list, recent_events_text: str) -> None:
    sections.extend([
        "",
        "【直近の出来事】",
        _RECENT_EVENTS_PREAMBLE,
        recent_events_text.strip() or _PLACEHOLDER_RECENT_EVENTS,
    ])


def _emit_relevant_memories(sections: list, relevant_memories_text: str) -> None:
    if relevant_memories_text.strip():
        sections.extend([
            "",
            "【関連する記憶】",
            relevant_memories_text.strip(),
        ])


def _emit_inventory(sections: list, inventory_text: str) -> None:
    if inventory_text.strip():
        sections.extend([
            "",
            "【所持・判明した物証】",
            inventory_text.strip(),
        ])


def _emit_learned(sections: list, learned_text: str) -> None:
    """Phase 1c: ``【関連する学び】`` (semantic top-K) を legacy 順序で挿入。

    objective の直後 (current_state より前) に来るよう、legacy formatter
    から呼ぶときの位置で使う。空なら section ごと省略。
    """
    if learned_text.strip():
        sections.extend([
            "",
            "【関連する学び】",
            learned_text.strip(),
        ])


def _emit_mid_summary(sections: list, mid_summary_text: str) -> None:
    """Phase 2: ``【最近の流れ】`` (L4 mid summary) を legacy 順序で挿入。

    learned の直後 (current_state より前) に来るよう、legacy formatter から
    呼ぶときの位置で使う。空なら section ごと省略。
    """
    if mid_summary_text.strip():
        sections.extend([
            "",
            "【最近の流れ】",
            mid_summary_text.strip(),
        ])


def _emit_long_summary(sections: list, long_summary_text: str) -> None:
    """Phase 3: ``【自己像と世界観】`` (L5 long summary) を legacy 順序で挿入。

    objective の直後 (learned より前) に来るよう、legacy formatter から
    呼ぶときの位置で使う。空なら section ごと省略。
    """
    if long_summary_text.strip():
        sections.extend([
            "",
            "【自己像と世界観】",
            long_summary_text.strip(),
        ])


def _format_stable_to_volatile(
    *,
    current_state_text: str,
    recent_events_text: str,
    relevant_memories_text: str,
    active_memos_text: str,
    objective_text: str,
    inventory_text: str,
    learned_text: str,
    mid_summary_text: str,
    long_summary_text: str,
) -> str:
    """Phase 0 default: 更新頻度の低い section から並べる。

    順序: objective → self_image (L5, Phase 3) → learned → mid_summary (L4) →
    memos → inventory → memories → recent_events → current_state。

    section 寿命 (cache 寿命の根拠):
    - L5 self_image: ~45 ターンに 1 回 (最も安定)
    - learned: cluster 昇格時のみ更新 (10+ ターン安定)
    - L4 mid_summary: 15 ターンに 1 世代追加・内容は確定後不変
    - memos: memo_add/done 時のみ
    - ... 末尾 current_state は毎ターン更新
    """
    sections: list[str] = []

    # 1. 現在の目的 (静的、空なら省略)
    _emit_objective(sections, objective_text)

    # 2. 自己像と世界観 (L5 long summary、空なら省略) ★ Phase 3
    # 最も更新頻度が低い (= prefix cache 寿命最長) ので objective の直後
    if long_summary_text.strip():
        sections.extend([
            "【自己像と世界観】",
            long_summary_text.strip(),
            "",
        ])

    # 3. 関連する学び (semantic top-K、空なら省略) ★ Phase 1c
    if learned_text.strip():
        sections.extend([
            "【関連する学び】",
            learned_text.strip(),
            "",
        ])

    # 4. 最近の流れ (L4 mid summary、空なら省略) ★ Phase 2
    if mid_summary_text.strip():
        sections.extend([
            "【最近の流れ】",
            mid_summary_text.strip(),
            "",
        ])

    # 4. 進行中のメモ (semi-static、空なら省略)
    if active_memos_text.strip():
        # objective が出た直後だと改行が二重になるので、ここでは先頭の空行を
        # 入れない。_emit_active_memos は先頭に "" を入れる前提なので使えない。
        sections.extend([
            "【進行中のメモ】",
            active_memos_text.strip(),
            "",
        ])

    # 4. 所持・判明した物証 (mid-volatile、空なら省略)
    if inventory_text.strip():
        sections.extend([
            "【所持・判明した物証】",
            inventory_text.strip(),
            "",
        ])

    # 5. 関連する記憶 (mid-volatile、空なら省略)
    if relevant_memories_text.strip():
        sections.extend([
            "【関連する記憶】",
            relevant_memories_text.strip(),
            "",
        ])

    # 6. 直近の出来事 (常に出す。空なら「（なし）」)
    sections.extend([
        "【直近の出来事】",
        _RECENT_EVENTS_PREAMBLE,
        recent_events_text.strip() or _PLACEHOLDER_RECENT_EVENTS,
        "",
    ])

    # 7. 現在地と周囲 (必須、最 volatile なので末尾)
    sections.extend([
        "【現在地と周囲】",
        current_state_text.strip() or _PLACEHOLDER_CURRENT_STATE,
    ])

    return "\n".join(sections)


def _format_legacy(
    *,
    current_state_text: str,
    recent_events_text: str,
    relevant_memories_text: str,
    active_memos_text: str,
    objective_text: str,
    inventory_text: str,
    learned_text: str,
    mid_summary_text: str,
    long_summary_text: str,
) -> str:
    """Issue #227 chore β 時代の旧順序。A/B 検証用に保持。

    順序: objective → long_summary (Phase 3) → learned (Phase 1c) →
    mid_summary (Phase 2) → current_state → memos → recent_events →
    memories → inventory。
    """
    sections: list[str] = []

    _emit_objective(sections, objective_text)
    _emit_long_summary(sections, long_summary_text)
    _emit_learned(sections, learned_text)
    _emit_mid_summary(sections, mid_summary_text)
    _emit_current_state(sections, current_state_text)
    _emit_active_memos(sections, active_memos_text)
    _emit_recent_events(sections, recent_events_text)
    _emit_relevant_memories(sections, relevant_memories_text)
    _emit_inventory(sections, inventory_text)

    return "\n".join(sections)
