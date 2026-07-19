"""コンテキストフォーマット戦略 (world_runtime format に統一)。"""

import logging
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
    4. **【直近の出来事】** — recent_events_text (append 中心で head 安定)
    5. **【前回の予測と実際】** — prediction_feedback_text (毎ターン直前 action 依存)
    6. **【関連する記憶】** — relevant_memories_text (cue 再計算で全変動しうる volatile)
    7. **【現在地と周囲】** — current_state_text (毎ターン更新の最 volatile / 必須)

    意図:
      - prefix cache は ④ までで止めたい (= 末尾 append の直近の出来事 は head 安定)。
        「関連する記憶」は cue 由来で毎ターン全変動しうるため、その下に置く。
      - 「現在地と周囲」を末尾に置くことで LLM の attention (Lost in the Middle,
        Liu et al. 2023) が末尾に強く向き、「今ここ」情報の重みが上がる。
      - 「関連する記憶」も末尾近くに置くと recall 内容への attention が高まり、
        副産物として hallucination 抑制効果が見込める。

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
        prediction_feedback_text: str = "",
        pending_predictions_text: str = "",
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
            ("prediction_feedback_text", prediction_feedback_text),
            ("pending_predictions_text", pending_predictions_text),
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
                prediction_feedback_text=prediction_feedback_text,
                pending_predictions_text=pending_predictions_text,
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
            prediction_feedback_text=prediction_feedback_text,
            pending_predictions_text=pending_predictions_text,
        )


# ──────────────────────────────────────────────────────────────────
# env var 由来の factory。実験スクリプトから A/B 切替する用途。
# ──────────────────────────────────────────────────────────────────


def resolve_section_order_from_env(
    env: Optional[Mapping[str, str]] = None,
) -> str:
    """``PROMPT_SECTION_ORDER`` 設定値から section 順序を解決する。

    実験スクリプト経由で A/B 検証する用途。``env`` を渡せばその dict を見る。
    ``env=None`` は古い呼び出し経路の取りこぼしとして失敗させる。

    - 値が未設定・空文字なら default の ``stable_to_volatile`` を返す
    - 値が未知の文字列なら ``ValueError`` (silent fallback 防止 / PR #433 経緯)

    Raises:
        ValueError: 未知の文字列のとき
    """
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )
    source = env
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


def _emit_prediction_feedback(sections: list, prediction_feedback_text: str) -> None:
    if prediction_feedback_text.strip():
        sections.extend([
            "",
            "【前回の予測と実際】",
            prediction_feedback_text.strip(),
        ])


def _emit_pending_predictions(sections: list, pending_predictions_text: str) -> None:
    """U10a (予測誤差統一設計 部品6): 【保留中の予測】section を emit する。

    【前回の予測と実際】の隣に置く (計画書の配置指定)。再浮上した pending が
    無ければ ``pending_predictions_text`` は空文字 (= section ごと省略)。
    """
    if pending_predictions_text.strip():
        sections.extend([
            "",
            "【保留中の予測】",
            pending_predictions_text.strip(),
        ])


def _emit_relevant_memories(sections: list, relevant_memories_text: str) -> None:
    """【関連する記憶】 section を emit する。

    受動想起 service が未注入なら ``relevant_memories_text`` は空文字
    (= section ごと省略)。注入されていれば最低でも「(受動想起では何も
    浮かばなかった)」が ``prompt_builder._run_passive_recall`` で生成
    されて渡る。"""
    if relevant_memories_text.strip():
        sections.extend([
            "",
            "【関連する記憶】(あなた自身の過去の体験として自動的に思い出されたもの)",
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
    prediction_feedback_text: str,
    pending_predictions_text: str = "",
) -> str:
    """Phase 0 default: 更新頻度の低い section から並べる。

    順序: objective → self_image (L5) → learned → mid_summary (L4) →
    recent_events → inventory → memos → prediction_feedback → memories →
    current_state。

    section 寿命 / 変動率の根拠 (Y_after_pr612 実測, tick 1-107):

    | section              | 変動率 (per tick) | 種類 |
    |----------------------|------------------|------|
    | objective            | 0% (静的)         | 純 stable |
    | L5 self_image        | ~45 tick に 1 回   | stable |
    | learned (semantic)   | cluster 昇格時のみ | stable |
    | L4 mid_summary       | 15 tick に 1 世代  | stable |
    | recent_events (head) | ~0% (末尾 append) | **head 安定** |
    | inventory            | 11-19%            | mid-volatile |
    | memos                | 23-43%            | high-volatile (agent 操作依存) |
    | prediction_feedback  | 0% or 100%        | (シナリオ依存、未使用なら空) |
    | recall (記憶)         | 19-32%            | volatile (cue 再計算) |
    | current_state        | ~100% (毎 tick)   | 最 volatile |

    順序の意図:
    - recent_events は **末尾 append-only で head は完全安定**。静的群の
      直後に置くことで「head 安定 prefix」を最大化する。一度 append された
      部分はそれ以降決して変わらないので、prompt 序盤に置くほど cache hit
      範囲が広がる
    - inventory / memos は agent 操作で頻繁に変動。recent_events の head
      安定 cache を破壊しないよう全部 recent_events の下に置く
    - recall は volatile だが「今ここで関連する記憶」を末尾近くに置くと
      attention が乗りやすい (Lost in the Middle)。current_state の直前
    - current_state は最 volatile なので末尾

    旧設計からの変更:
    - PR #614 初版では memos のみ recent_events の下に下げた
    - 本版で inventory も recent_events の下に下げる: 実測で inventory も
      11-19% 変動 (memos より少ないが non-trivial)。両方下に集約することで
      静的群 + recent_events までの prefix を完全に safe にする
    """
    sections: list[str] = []

    # 1. 現在の目的 (静的、空なら省略)
    _emit_objective(sections, objective_text)

    # 2. 自己像と世界観 (L5 long summary、空なら省略)
    # 最も更新頻度が低い (= prefix cache 寿命最長) ので objective の直後
    if long_summary_text.strip():
        sections.extend([
            "【自己像と世界観】",
            long_summary_text.strip(),
            "",
        ])

    # 3. 関連する学び (semantic top-K、空なら省略)
    if learned_text.strip():
        sections.extend([
            "【関連する学び】",
            learned_text.strip(),
            "",
        ])

    # 4. 最近の流れ (L4 mid summary、空なら省略)
    if mid_summary_text.strip():
        sections.extend([
            "【最近の流れ】",
            mid_summary_text.strip(),
            "",
        ])

    # 5. 直近の出来事 (常に出す。空なら「（なし）」)
    # 末尾 append 中心で **head は完全安定** (一度 append された行は決して
    # 変わらない)。静的群の直後に置くことで「objective + L5 + learned +
    # L4 + recent_events の head」までを stable prefix として cache hit
    # させる。inventory / memos / recall を上に置くと、それらの変動で
    # recent_events の head 安定 cache が破壊される。
    sections.extend([
        "【直近の出来事】",
        _RECENT_EVENTS_PREAMBLE,
        recent_events_text.strip() or _PLACEHOLDER_RECENT_EVENTS,
        "",
    ])

    # 6. 所持・判明した物証 (mid-volatile、空なら省略)
    # 実測で 11-19% 変動 (= survival シナリオで pickup が断続的)。
    # recent_events の head 安定 cache を守るため下に集約。
    if inventory_text.strip():
        sections.extend([
            "【所持・判明した物証】",
            inventory_text.strip(),
            "",
        ])

    # 7. 進行中のメモ (high-volatile、空なら省略)
    # 旧設計では「memo 操作時のみ」と semi-static 扱いで上位 (memos →
    # inventory → recent_events の順) に置いていたが、Y_after_pr612 実測で
    # 23-43% 変動 (= agent が頻繁に memo_add/done を呼ぶと tick 単位で
    # 大きく上下) と判明。volatile section 群 (inventory, memos) は
    # 全部 recent_events の下に集約する。
    if active_memos_text.strip():
        sections.extend([
            "【進行中のメモ】",
            active_memos_text.strip(),
            "",
        ])

    # 8. 前回の予測と実際 (空なら省略)
    # 毎ターン直前 action 依存で volatile (= 100% 変動)。シナリオが
    # expected_result_policy=off なら常時空。
    if prediction_feedback_text.strip():
        sections.extend([
            "【前回の予測と実際】",
            prediction_feedback_text.strip(),
            "",
        ])

    # 8b. 保留中の予測 (U10a / 部品6、空なら省略)
    # 【前回の予測と実際】の隣に置く (計画書の配置指定)。再浮上しなければ
    # flag ON でも常に空 (= section ごと省略)。
    if pending_predictions_text.strip():
        sections.extend([
            "【保留中の予測】",
            pending_predictions_text.strip(),
            "",
        ])

    # 9. 関連する記憶 (volatile、cue 再計算で 19-32% 変動)
    # 受動想起 service が未注入なら空文字 → section ごと省略。
    # 末尾近くに置くことで「今ここで関連する記憶」への attention を強める
    # (Lost in the Middle 緩和)。
    if relevant_memories_text.strip():
        sections.extend([
            "【関連する記憶】(あなた自身の過去の体験として自動的に思い出されたもの)",
            relevant_memories_text.strip(),
            "",
        ])

    # 10. 現在地と周囲 (必須、最 volatile なので末尾)
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
    prediction_feedback_text: str,
    pending_predictions_text: str = "",
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
    _emit_prediction_feedback(sections, prediction_feedback_text)
    _emit_pending_predictions(sections, pending_predictions_text)
    _emit_recent_events(sections, recent_events_text)
    _emit_relevant_memories(sections, relevant_memories_text)
    _emit_inventory(sections, inventory_text)

    return "\n".join(sections)
