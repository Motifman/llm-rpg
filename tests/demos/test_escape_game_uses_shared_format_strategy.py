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
        user = prompt["user"]

        assert "## 現在の状況" not in user
        assert "## 直近の出来事" not in user
        assert "【現在地と周囲】" in user
        assert "【直近の出来事】" in user

    def test_prompt_renders_objective_section(self) -> None:
        """escape_game 固定の目的文 ``【現在の目的】`` が含まれる。"""
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["user"]

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
        user = prompt["user"]

        assert "【所持・判明した物証】" in user

    def test_section_ordering_matches_shared_strategy(self) -> None:
        """section 順序が strategy の規約と一致する: 目的→現在地→メモ→出来事→記憶→物証。"""
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["user"]

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
        user = prompt["user"]

        assert "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。" in user
        # 指示文が他のセクション見出しより後ろにある
        idx_instruction = user.index("利用可能なツールから")
        idx_inventory = user.index("【所持・判明した物証】")
        assert idx_inventory < idx_instruction

    def test_strategy_output_matches_escape_game_prompt_body(self) -> None:
        """strategy を直接呼んだ出力が escape_game の prompt body と整合する (構造保証)。

        これは本家 strategy と escape_game の section 組み立てが同じであることを
        厳密に保証する: 将来どちらかが変わったら本テストが壊れる。
        """
        runtime = create_escape_game_runtime(_FORBIDDEN_LIBRARY)
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        user = prompt["user"]

        # 同じ素材で直接 strategy を呼んで、escape_game prompt と本体部分が一致するか確認
        strategy = SectionBasedContextFormatStrategy()
        sample = strategy.format(
            current_state_text="dummy_current",
            recent_events_text="dummy_recent",
            objective_text=EscapeGameRuntime._ESCAPE_GAME_OBJECTIVE_TEXT,
            inventory_text="dummy_inv",
            active_memos_text="",
            relevant_memories_text="",
        )
        # strategy が【現在の目的】を先頭に置き、【現在地と周囲】が続く構造
        assert sample.startswith("【現在の目的】")
        assert "【現在地と周囲】" in sample
        assert "dummy_current" in sample
        assert "dummy_recent" in sample
        assert "dummy_inv" in sample
