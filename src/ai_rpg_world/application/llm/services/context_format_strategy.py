"""コンテキストフォーマット戦略 (world_runtime format に統一)。"""

from ai_rpg_world.application.llm.contracts.interfaces import IContextFormatStrategy
from ai_rpg_world.being.application.episode_index_text import EPISODE_INDEX_HEADING


class SectionBasedContextFormatStrategy(IContextFormatStrategy):
    """``【...】`` 見出し形式でコンテキストを組み立てる戦略。

    Issue #356 後続 (Phase 0): prefix cache 効率と Lost-in-the-middle 緩和を
    目的に section の並び順を見直した。更新頻度の低い section を上に、毎ターン
    変動する section を末尾近くに置く。

    詳細根拠は ``docs/memory_system/short_term_memory_design.md`` §5。

    ## 並び

    1. **【現在の目的】** — objective_text (scenario 固定の目標文)
    1b. **【知っている人】** — known_people_text (Being が知っている人。新しい人を知ったときだけ変わる)
    2. **【自己像と世界観】** — long_summary_text (L5)
    3. **【最近の流れ】** — mid_summary_text (L4)
    4. **【直近の出来事】** — recent_events_text (append 中心で head 安定)
    5b. **【思い出せる出来事】** — episode_index_text (エピソードの目次。書き起こしと呼び出しのときだけ変わる)
    6. **【メモ】** — being_memo_text (Being のメモ帳、#1628)
    7. **【現在地と周囲】** — current_state_text (所持品を含む最 volatile / 必須)

    意図:
      - prefix cache は直近の出来事の安定した先頭まで残す。
      - 「現在地と周囲」を末尾に置くことで LLM の attention (Lost in the Middle,
        Liu et al. 2023) が末尾に強く向き、「今ここ」情報の重みが上がる。
    """

    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        objective_text: str = "",
        inventory_text: str = "",
        mid_summary_text: str = "",
        long_summary_text: str = "",
        known_people_text: str = "",
        episode_index_text: str = "",
        being_memo_text: str = "",
    ) -> str:
        for name, value in (
            ("current_state_text", current_state_text),
            ("recent_events_text", recent_events_text),
            ("objective_text", objective_text),
            ("inventory_text", inventory_text),
            ("mid_summary_text", mid_summary_text),
            ("long_summary_text", long_summary_text),
            ("known_people_text", known_people_text),
            ("episode_index_text", episode_index_text),
            ("being_memo_text", being_memo_text),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{name} must be str")

        return _format_stable_to_volatile(
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            objective_text=objective_text,
            inventory_text=inventory_text,
            mid_summary_text=mid_summary_text,
            long_summary_text=long_summary_text,
            known_people_text=known_people_text,
            episode_index_text=episode_index_text,
            being_memo_text=being_memo_text,
        )


_PLACEHOLDER_CURRENT_STATE = "（情報なし）"
_PLACEHOLDER_RECENT_EVENTS = "（なし）"
_RECENT_EVENTS_PREAMBLE = "観測（世界から届いた事象）と、あなた自身の行動の結果が時系列に並びます。"


def _emit_objective(sections: list[str], objective_text: str) -> None:
    if objective_text.strip():
        sections.extend([
            "【現在の目的】",
            objective_text.strip(),
            "",
        ])


def _emit_known_people(sections: list[str], known_people_text: str) -> None:
    """目的の次に変わりにくい。新しい人を知ったときだけ、この節から後ろが変わる。"""
    if known_people_text.strip():
        sections.extend([
            "【知っている人】",
            known_people_text.strip(),
            "",
        ])


def _emit_current_state(sections: list[str], current_state_text: str) -> None:
    sections.extend([
        "【現在地と周囲】",
        current_state_text.strip() or _PLACEHOLDER_CURRENT_STATE,
    ])


def _emit_episode_index(sections: list[str], episode_index_text: str) -> None:
    if episode_index_text.strip():
        sections.extend(["", EPISODE_INDEX_HEADING, episode_index_text.rstrip()])


def _emit_being_memo(sections: list[str], being_memo_text: str) -> None:
    if being_memo_text.strip():
        sections.extend(["", "【メモ】", being_memo_text.rstrip()])


def _emit_recent_events(sections: list[str], recent_events_text: str) -> None:
    sections.extend([
        "",
        "【直近の出来事】",
        _RECENT_EVENTS_PREAMBLE,
        recent_events_text.strip() or _PLACEHOLDER_RECENT_EVENTS,
    ])


def _emit_mid_summary(sections: list[str], mid_summary_text: str) -> None:
    """``【最近の流れ】`` (L4 mid summary) を呼び出し位置へ挿入する。"""
    if mid_summary_text.strip():
        sections.extend([
            "",
            "【最近の流れ】",
            mid_summary_text.strip(),
        ])


def _emit_long_summary(sections: list[str], long_summary_text: str) -> None:
    """``【自己像と世界観】`` (L5 long summary) を呼び出し位置へ挿入する。"""
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
    objective_text: str,
    inventory_text: str,
    mid_summary_text: str,
    long_summary_text: str,
    known_people_text: str = "",
    episode_index_text: str = "",
    being_memo_text: str = "",
) -> str:
    """Phase 0 default: 更新頻度の低い section から並べる。

    順序: objective → self_image (L5) → mid_summary (L4) → recent_events →
    memos → current_state。

    section 寿命 / 変動率の根拠 (Y_after_pr612 実測, tick 1-107):

    | section              | 変動率 (per tick) | 種類 |
    |----------------------|------------------|------|
    | objective            | 0% (静的)         | 純 stable |
    | L5 self_image        | ~45 tick に 1 回   | stable |
    | L4 mid_summary       | 15 tick に 1 世代  | stable |
    | recent_events (head) | ~0% (末尾 append) | **head 安定** |
    | memos                | 23-43%            | high-volatile (agent 操作依存) |
    | current_state        | ~100% (毎 tick)   | 最 volatile |

    順序の意図:
    - recent_events は **末尾 append-only で head は完全安定**。静的群の
      直後に置くことで「head 安定 prefix」を最大化する。一度 append された
      部分はそれ以降決して変わらないので、prompt 序盤に置くほど cache hit
      範囲が広がる
    - memos は agent 操作で頻繁に変動するため直近の出来事より後ろへ置く
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
    _emit_known_people(sections, known_people_text)

    # 2. 自己像と世界観 (L5 long summary、空なら省略)
    # 最も更新頻度が低い (= prefix cache 寿命最長) ので objective の直後
    if long_summary_text.strip():
        sections.extend([
            "【自己像と世界観】",
            long_summary_text.strip(),
            "",
        ])

    # 3. 最近の流れ (L4 mid summary、空なら省略)
    if mid_summary_text.strip():
        sections.extend([
            "【最近の流れ】",
            mid_summary_text.strip(),
            "",
        ])

    # 4. 直近の出来事 (常に出す。空なら「（なし）」)
    # 末尾 append 中心で **head は完全安定** (一度 append された行は決して
    # 変わらない)。静的群の直後に置くことで「objective + L5 + L4 +
    # recent_events の head」までを stable prefix として cache hit
    # させる。memos を上に置くと、その変動で
    # recent_events の head 安定 cache が破壊される。
    sections.extend([
        "【直近の出来事】",
        _RECENT_EVENTS_PREAMBLE,
        recent_events_text.strip() or _PLACEHOLDER_RECENT_EVENTS,
        "",
    ])

    # 5b. 思い出せる出来事 (エピソードの目次、#1623)。書き起こしと呼び出しのときだけ
    # 変わるので、毎ターン伸びる直近の出来事より後ろ、メモより前に置く。
    if episode_index_text.strip():
        sections.extend([EPISODE_INDEX_HEADING, episode_index_text.rstrip(), ""])

    # 6. メモ帳 (#1628、high-volatile、空なら省略)
    if being_memo_text.strip():
        sections.extend([
            "【メモ】",
            being_memo_text.rstrip(),
            "",
        ])

    # 7. 現在地と周囲 (必須、最 volatile なので末尾)
    sections.extend([
        "【現在地と周囲】",
        current_state_text.strip() or _PLACEHOLDER_CURRENT_STATE,
    ])
    return "\n".join(sections)
