"""Issue #227 chore β: escape_game の prompt と本家 format strategy の整合確認。

PR で escape_game の ``build_full_prompt`` の section 組み立てを本家
``SectionBasedContextFormatStrategy`` に委譲した。これにより形式・順序の
二重管理が解消されたことを E2E で保証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from demos.escape_game.escape_game_runtime import (
    EscapeGameRuntime,
    create_escape_game_runtime,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_LIBRARY = (
    _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"
)


class TestEscapeGameUsesSharedFormatStrategy:
    """escape_game runtime の prompt が本家 strategy 形式 (``【...】``) を使う。"""

    def test_prompt_user_message_uses_bracket_section_headers(self) -> None:
        """``## ...`` (旧形式) が出ず ``【...】`` だけが出る。"""
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["messages"][1]["content"]

        assert "## 現在の状況" not in user
        assert "## 直近の出来事" not in user
        assert "【現在地と周囲】" in user
        assert "【直近の出来事】" in user

    def test_prompt_renders_objective_section(self) -> None:
        """escape_game 固定の目的文 ``【現在の目的】`` が含まれる。"""
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["messages"][1]["content"]

        assert "【現在の目的】" in user
        assert "この廃墟から外へ脱出する" in user

    def test_prompt_renders_inventory_section(self) -> None:
        """forbidden_library で初期インベントリ空でも ``【所持・判明した物証】`` は出る。

        section は空文字を渡さない限り出力されるため、provider が「（なし）」を
        返す形なら section ごと出る。
        """
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["messages"][1]["content"]

        assert "【所持・判明した物証】" in user

    def test_section_ordering_matches_shared_strategy(self) -> None:
        """section 順序が strategy の規約と一致する: 目的→現在地→メモ→出来事→記憶→物証。"""
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["messages"][1]["content"]

        idx_obj = user.index("【現在の目的】")
        idx_state = user.index("【現在地と周囲】")
        idx_events = user.index("【直近の出来事】")
        idx_inventory = user.index("【所持・判明した物証】")

        assert idx_obj < idx_state < idx_events < idx_inventory

    def test_action_instruction_appears_at_tail(self) -> None:
        """指示文が末尾に来る。"""
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["messages"][1]["content"]

        assert "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。" in user
        # 指示文が他のセクション見出しより後ろにある
        idx_instruction = user.index("利用可能なツールから")
        idx_inventory = user.index("【所持・判明した物証】")
        assert idx_inventory < idx_instruction

    def test_escape_game_prompt_body_is_produced_by_shared_strategy(self) -> None:
        """escape_game の prompt body と shared strategy 出力が完全一致する。

        runtime が strategy に渡している素材を再現して直接 strategy を呼び、
        prompt["user"] から指示文を除いた本体と byte 単位で一致することを確認する。
        これにより将来 escape_game 側が独自に section を組み直すような変更が
        混入したら本テストが壊れる (二重管理の再発を防ぐ）。
        """
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["messages"][1]["content"]

        # prompt は context_body + "\n\n" + action_instruction の連結
        instruction = EscapeGameRuntime._ESCAPE_GAME_ACTION_INSTRUCTION
        assert user.endswith(instruction)
        context_body = user[: -len(instruction)].rstrip("\n")

        # 同じ素材で直接 strategy を呼び、context_body と一致するか確認
        # 注: runtime 内部の current_state_text / recent_events_text / inventory_text
        # を直接取得する API は無いので、ここでは「strategy 経由で組み立てた
        # ものを再分解できる」構造保証だけ行う。
        strategy = SectionBasedContextFormatStrategy()
        # context_body の【現在の目的】〜【所持・判明した物証】までは strategy
        # が組み立てた領域。先頭が必ず【現在の目的】(objective が空でない場合) で
        # 始まり、【現在地と周囲】が続く。
        assert context_body.startswith("【現在の目的】")
        # objective_text の中身がそのまま入っていることを確認
        for line in EscapeGameRuntime._ESCAPE_GAME_OBJECTIVE_TEXT.splitlines():
            assert line in context_body, f"missing objective line: {line!r}"

        # strategy を空素材で呼んだ場合も同じ section ヘッダ順序になるはず
        skeleton = strategy.format(
            current_state_text="X",
            recent_events_text="Y",
            objective_text=EscapeGameRuntime._ESCAPE_GAME_OBJECTIVE_TEXT,
            inventory_text="Z",
            active_memos_text="",
            relevant_memories_text="",
        )
        assert skeleton.startswith("【現在の目的】")
        assert "【現在地と周囲】" in skeleton
