"""
LLM の tool 名 typo を救済する仕組みのテスト (PR-J)。

無人島シナリオ実走 (Y) で `speech_speech` / `spot_graph_gather` 等の typo が
5 件発生し、`UNSUPPORTED_TOOL` に化けて生存危機の発話が世界に届かない silent
failure になっていた。本 PR で:

1. `UNSUPPORTED_TOOL` を `_RESCHEDULE_ERROR_CODES` に追加 (= 次 tick で起床)
2. エラーメッセージに fuzzy match suggestion + valid tool 一覧を含めて agent
   に修正ヒントを届ける

PR-I で導入した `max_self_reschedule_streak` (= 5) が soft cap として効く。
5 連続 typo すると streak pop で chain は終わり、外部観測の起床に戻る。
"""

import pytest

from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    build_unsupported_tool_message,
    suggest_closest_tool_name,
)


class TestSuggestClosestToolName:
    """fuzzy match で typo → 正しい tool 名候補を出す。"""

    def test_minor_typo_returns_close_match(self):
        """1-2 文字違いの typo は正しい候補を返す。"""
        # PR-DD で speech_speak → speak にリネームしたので、fuzzy 対象を
        # 別 tool の typo に変える。実際に PR #638 直後の run で LLM が
        # `spot_graph_travrl_to` (l → r 誤打) を発明する可能性を模する。
        valid = ["spot_graph_travel_to", "spot_graph_explore", "speak"]
        assert (
            suggest_closest_tool_name("spot_graph_travrl_to", valid)
            == "spot_graph_travel_to"
        )

    def test_shortened_name_returns_full_name(self):
        """短縮形 (e.g. ``spot_graph_pickup``) は ``spot_graph_pickup_item`` を返す。"""
        valid = ["spot_graph_pickup_item", "spot_graph_drop_item"]
        assert suggest_closest_tool_name("spot_graph_pickup", valid) == "spot_graph_pickup_item"

    def test_imaginary_tool_returns_none(self):
        """LLM が想像で作った tool 名 (近い候補なし) は None を返す。
        prefix segment 一致 + suffix ratio cutoff=0.5 で `gather` / `harvest`
        のような独立した語は救わない。"""
        valid = ["spot_graph_explore", "spot_graph_travel_to", "spot_graph_wait"]
        # spot_graph_gather: prefix `spot_graph` は一致するが suffix
        # `gather` vs (`explore` / `travel_to` / `wait`) の ratio は全て
        # 0.5 未満なので None になる (= 想像由来 typo を fuzzy で救わない)。
        assert suggest_closest_tool_name("spot_graph_gather", valid) is None
        assert suggest_closest_tool_name("spot_graph_harvest", valid) is None

    def test_very_short_input_returns_none(self):
        """極端に短い入力 (e.g. ``say``) は cutoff を超える match が無く None。"""
        valid = ["spot_graph_travel_to", "spot_graph_explore"]
        assert suggest_closest_tool_name("say", valid) is None

    def test_empty_valid_returns_none(self):
        """valid 一覧が空なら何も提案しない。"""
        assert suggest_closest_tool_name("speak", []) is None


class TestBuildUnsupportedToolMessage:
    """エラーメッセージに fuzzy suggestion と valid 一覧を含める。"""

    def test_message_contains_typoed_name(self):
        msg = build_unsupported_tool_message(
            requested="spot_graph_travrl_to",
            valid_tools=["spot_graph_travel_to"],
        )
        assert "spot_graph_travrl_to" in msg

    def test_message_contains_fuzzy_suggestion_when_close(self):
        """近い候補がある時、「もしかして」風のヒントを含む。"""
        msg = build_unsupported_tool_message(
            requested="spot_graph_travrl_to",
            valid_tools=["spot_graph_travel_to", "spot_graph_explore"],
        )
        assert "spot_graph_travel_to" in msg
        # 日本語の修正ヒントが含まれる
        assert "もしかして" in msg or "did you mean" in msg.lower()

    def test_message_contains_valid_tools_list(self):
        """近い候補が無くても valid 一覧を必ず含めることで、LLM が次 tick で
        正しい tool を選び直せるようにする。"""
        msg = build_unsupported_tool_message(
            requested="spot_graph_gather",
            valid_tools=["spot_graph_explore", "spot_graph_wait", "memo_add"],
        )
        for valid_name in ("spot_graph_explore", "spot_graph_wait", "memo_add"):
            assert valid_name in msg


class TestUnsupportedToolIsReschedulable:
    """UNSUPPORTED_TOOL が _RESCHEDULE_ERROR_CODES に含まれる。"""

    def test_unsupported_tool_is_reschedulable(self):
        from ai_rpg_world.application.llm.contracts.dtos import (
            is_reschedulable_error_code,
        )
        assert is_reschedulable_error_code("UNSUPPORTED_TOOL")


class TestExecuteToolReturnsReschedulableDto:
    """_execute_tool が UNSUPPORTED_TOOL を返すとき、DTO の should_reschedule=True
    が立っている。fuzzy suggestion と valid 一覧も message に含む。"""

    def test_execute_tool_unknown_returns_should_reschedule_true(self, monkeypatch, tmp_path):
        # 単体テスト用に最小 session を構築
        from tests.demos.test_world_runtime_dispatch_table import _create_session
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        state = _create_session(monkeypatch, tmp_path)
        wiring = state.llm_wiring
        pid = state.runtime.get_player_ids()[0]

        result = wiring._execute_tool(
            pid, "spot_graph_travrl_to", {"destination_label": "拠点"}, None
        )
        assert result.success is False
        assert result.error_code == "UNSUPPORTED_TOOL"
        assert result.should_reschedule is True

    def test_execute_tool_unknown_message_has_suggestion_and_valid_list(
        self, monkeypatch, tmp_path
    ):
        from tests.demos.test_world_runtime_dispatch_table import _create_session

        state = _create_session(monkeypatch, tmp_path)
        wiring = state.llm_wiring
        pid = state.runtime.get_player_ids()[0]

        result = wiring._execute_tool(
            pid, "spot_graph_travrl_to", {"destination_label": "拠点"}, None
        )
        # message に typoed name は含まれる
        assert "spot_graph_travrl_to" in result.message
        # 近い候補 spot_graph_travel_to がメッセージに含まれる (= fuzzy suggestion)
        assert "spot_graph_travel_to" in result.message
        # valid 一覧も含まれる (= memo_add などが含まれているか確認)
        assert "memo_add" in result.message


class TestInvalidDestinationLabelIsReschedulable:
    """Player 3 沈黙の副次原因: `_handle_travel_to` で
    `INVALID_DESTINATION_LABEL` を返すとき、DTO の `should_reschedule` が
    立っていなかった (= `_RESCHEDULE_ERROR_CODES` に enum が居るのに ハンドラ
    側が `should_reschedule_for_next_tick()` を呼んでいない)。"""

    def test_invalid_destination_label_dto_has_should_reschedule_true(
        self, monkeypatch, tmp_path
    ):
        from tests.demos.test_world_runtime_dispatch_table import _create_session
        from types import SimpleNamespace

        state = _create_session(monkeypatch, tmp_path)
        wiring = state.llm_wiring
        pid = state.runtime.get_player_ids()[0]

        # runtime_context の targets は空。実在しないラベルを送ると
        # ToolArgumentResolutionException → INVALID_DESTINATION_LABEL に化ける。
        runtime_context = SimpleNamespace(targets={})
        result = wiring._handle_travel_to(
            pid, {"destination_label": "存在しない場所"}, runtime_context
        )
        assert result.success is False
        assert result.error_code == "INVALID_DESTINATION_LABEL"
        assert result.should_reschedule is True, (
            "INVALID_DESTINATION_LABEL は _RESCHEDULE_ERROR_CODES に居るが、"
            "ハンドラ側の DTO 構築で should_reschedule を立て忘れていた。"
        )
