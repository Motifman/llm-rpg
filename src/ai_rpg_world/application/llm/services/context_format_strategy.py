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
    5. **【関連する学び】** — learned_text (semantic top-K)
    6. **【関連する記憶】** — relevant_memories_text (想起見出しを内包)
    6b. **【思い出せる出来事】** — episode_index_text (エピソードの目次。書き起こしと呼び出しのときだけ変わる)
    7. **【進行中のメモ】** — active_memos_text
    8. **【現在地と周囲】** — current_state_text (所持品を含む最 volatile / 必須)

    意図:
      - prefix cache は直近の出来事の安定した先頭まで残す。semantic top-K と
        「関連する記憶」は毎ターン再計算されるため、その下に置く。
      - 「現在地と周囲」を末尾に置くことで LLM の attention (Lost in the Middle,
        Liu et al. 2023) が末尾に強く向き、「今ここ」情報の重みが上がる。
      - 「関連する記憶」も末尾近くに置くと recall 内容への attention が高まり、
        副産物として hallucination 抑制効果が見込める。
    """

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
        known_people_text: str = "",
        episode_index_text: str = "",
        being_memo_text: str = "",
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
            ("known_people_text", known_people_text),
            ("episode_index_text", episode_index_text),
            ("being_memo_text", being_memo_text),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{name} must be str")

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


def _emit_active_memos(sections: list[str], active_memos_text: str) -> None:
    if active_memos_text.strip():
        sections.extend([
            "",
            "【進行中のメモ】",
            active_memos_text.strip(),
        ])


def _emit_recent_events(sections: list[str], recent_events_text: str) -> None:
    sections.extend([
        "",
        "【直近の出来事】",
        _RECENT_EVENTS_PREAMBLE,
        recent_events_text.strip() or _PLACEHOLDER_RECENT_EVENTS,
    ])


def _emit_relevant_memories(sections: list[str], relevant_memories_text: str) -> None:
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


def _emit_learned(sections: list[str], learned_text: str) -> None:
    """``【関連する学び】`` (semantic top-K) を呼び出し位置へ挿入する。"""
    if learned_text.strip():
        sections.extend([
            "",
            "【関連する学び】",
            learned_text.strip(),
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
    relevant_memories_text: str,
    active_memos_text: str,
    objective_text: str,
    inventory_text: str,
    learned_text: str,
    mid_summary_text: str,
    long_summary_text: str,
    known_people_text: str = "",
    episode_index_text: str = "",
    being_memo_text: str = "",
) -> str:
    """Phase 0 default: 更新頻度の低い section から並べる。

    順序: objective → self_image (L5) → mid_summary (L4) → recent_events →
    learned → memories → memos →
    current_state。

    section 寿命 / 変動率の根拠 (Y_after_pr612 実測, tick 1-107):

    | section              | 変動率 (per tick) | 種類 |
    |----------------------|------------------|------|
    | objective            | 0% (静的)         | 純 stable |
    | L5 self_image        | ~45 tick に 1 回   | stable |
    | L4 mid_summary       | 15 tick に 1 世代  | stable |
    | recent_events (head) | ~0% (末尾 append) | **head 安定** |
    | learned (semantic)   | 36-62%            | volatile (top-K 再計算) |
    | recall (記憶)         | 19-32%            | volatile (cue 再計算) |
    | memos                | 23-43%            | high-volatile (agent 操作依存) |
    | current_state        | ~100% (毎 tick)   | 最 volatile |

    順序の意図:
    - recent_events は **末尾 append-only で head は完全安定**。静的群の
      直後に置くことで「head 安定 prefix」を最大化する。一度 append された
      部分はそれ以降決して変わらないので、prompt 序盤に置くほど cache hit
      範囲が広がる
    - semantic top-K は score の recency 項で毎回再計算されるため L4 より
      揮発する。出来事と予測の後ろで、episodic recall と隣接させる
    - recall は直近の出来事に引き起こされるため、出来事より後ろへ置く
    - memos は agent 操作で頻繁に変動するため想起群より後ろへ置く
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
    # させる。learned / memos / recall を上に置くと、それらの変動で
    # recent_events の head 安定 cache が破壊される。
    sections.extend([
        "【直近の出来事】",
        _RECENT_EVENTS_PREAMBLE,
        recent_events_text.strip() or _PLACEHOLDER_RECENT_EVENTS,
        "",
    ])

    # 6. 関連する学び (semantic top-K、空なら省略)
    # score で top-K を選ぶが、表示順は entry_id で安定化されている。
    if learned_text.strip():
        sections.extend([
            "【関連する学び】",
            learned_text.strip(),
            "",
        ])

    # 7. 関連する記憶 (volatile、cue 再計算で 19-32% 変動)
    # 受動想起 service が未注入なら空文字 → section ごと省略。
    # 末尾近くに置くことで「今ここで関連する記憶」への attention を強める
    # (Lost in the Middle 緩和)。
    if relevant_memories_text.strip():
        sections.extend([
            "【関連する記憶】(あなた自身の過去の体験として自動的に思い出されたもの)",
            relevant_memories_text.strip(),
            "",
        ])

    # 7b. 思い出せる出来事 (エピソードの目次、#1623)。書き起こしと呼び出しのときだけ
    # 変わるので、毎ターン伸びる直近の出来事より後ろ、メモより前に置く。
    if episode_index_text.strip():
        sections.extend([EPISODE_INDEX_HEADING, episode_index_text.rstrip(), ""])

    # 8. 進行中のメモ (high-volatile、空なら省略)
    if active_memos_text.strip():
        sections.extend([
            "【進行中のメモ】",
            active_memos_text.strip(),
            "",
        ])
    # 8b. メモ帳 (#1628)。進行中のメモと同じ位置。両方を出す設定は起動前に止めている。
    if being_memo_text.strip():
        sections.extend([
            "【メモ】",
            being_memo_text.rstrip(),
            "",
        ])

    # 9. 現在地と周囲 (必須、最 volatile なので末尾)
    sections.extend([
        "【現在地と周囲】",
        current_state_text.strip() or _PLACEHOLDER_CURRENT_STATE,
    ])
    return "\n".join(sections)
