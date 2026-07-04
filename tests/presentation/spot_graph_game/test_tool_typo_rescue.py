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
        valid = ["speech_speak", "speech_whisper", "travel_to"]
        assert suggest_closest_tool_name("speech_speech", valid) == "speech_speak"

    def test_shortened_name_returns_full_name(self):
        """短縮形 (e.g. ``pickup``) は ``pickup_item`` を返す。

        PR-CC (Y_after_pr639_640 後続): 旧例は ``spot_graph_pickup`` →
        ``spot_graph_pickup_item`` だったが、``spot_graph_`` prefix 廃止に
        伴い bare 短縮形に更新。
        """
        valid = ["pickup_item", "drop_item"]
        assert suggest_closest_tool_name("pickup", valid) == "pickup_item"

    def test_legacy_prefix_habit_is_rescued(self):
        """PR-CC (Y_after_pr639_640 後続、code-review HIGH 反映): LLM が数 tick
        の間 旧 ``spot_graph_`` prefix 付きで tool を呼んでくる可能性が高い。
        prefix を剥がした版でも fuzzy match を試み、bare 名の valid tool
        に救済する経路を保証する。

        ``suggest_closest_tool_name`` の実装が prefix strip を候補として
        追加する経路をここで固定する (retrograde regression 対策)。
        """
        valid = ["pickup_item", "drop_item", "travel_to"]
        # LLM の旧習慣 typo → bare 版 pickup_item に救済
        assert (
            suggest_closest_tool_name("spot_graph_pickup", valid) == "pickup_item"
        )
        # 完全 legacy 名 (spot_graph_interact) も interact に救済される
        assert (
            suggest_closest_tool_name("spot_graph_travel_to", valid + ["travel_to"])
            == "travel_to"
        )

    def test_legacy_prefix_habit_still_rejects_imaginary_tools(self):
        """旧 prefix + 存在しない tool 名 (= 想像) は依然として None。
        rescue 経路は valid にある名前へのみ働く安全網。"""
        valid = ["explore", "travel_to", "wait"]
        assert suggest_closest_tool_name("spot_graph_gather", valid) is None
        assert suggest_closest_tool_name("spot_graph_harvest", valid) is None

    def test_imaginary_tool_returns_none(self):
        """LLM が想像で作った tool 名 (近い候補なし) は None を返す。
        prefix segment 一致 + suffix ratio cutoff=0.5 で `gather` / `harvest`
        のような独立した語は救わない。

        PR-CC 後: 旧 prefix 剥がし経路が入っても、``spot_graph_gather`` →
        ``gather`` に剥がした後、valid の bare 名 (explore / travel_to /
        wait) と 1 segment 目が一致しないため ``common=0`` で候補除外され、
        None になる (=「想像由来 typo は救わない」性質を維持)。
        """
        valid = ["explore", "travel_to", "wait"]
        assert suggest_closest_tool_name("spot_graph_gather", valid) is None
        assert suggest_closest_tool_name("harvest", valid) is None

    def test_very_short_input_returns_none(self):
        """極端に短い入力 (e.g. ``say``) は cutoff を超える match が無く None。"""
        valid = ["speech_speak", "speech_whisper"]
        assert suggest_closest_tool_name("say", valid) is None

    def test_empty_valid_returns_none(self):
        """valid 一覧が空なら何も提案しない。"""
        assert suggest_closest_tool_name("speech_speak", []) is None


class TestBuildUnsupportedToolMessage:
    """エラーメッセージに fuzzy suggestion と valid 一覧を含める。"""

    def test_message_contains_typoed_name(self):
        msg = build_unsupported_tool_message(
            requested="speech_speech",
            valid_tools=["speech_speak"],
        )
        assert "speech_speech" in msg

    def test_message_contains_fuzzy_suggestion_when_close(self):
        """近い候補がある時、「もしかして」風のヒントを含む。"""
        msg = build_unsupported_tool_message(
            requested="speech_speech",
            valid_tools=["speech_speak", "speech_whisper"],
        )
        assert "speech_speak" in msg
        # 日本語の修正ヒントが含まれる
        assert "もしかして" in msg or "did you mean" in msg.lower()

    def test_message_contains_valid_tools_list(self):
        """近い候補が無くても valid 一覧を必ず含めることで、LLM が次 tick で
        正しい tool を選び直せるようにする。"""
        msg = build_unsupported_tool_message(
            requested="spot_graph_gather",
            valid_tools=["explore", "wait", "memo_add"],
        )
        for valid_name in ("explore", "wait", "memo_add"):
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
            pid, "speech_speech", {"channel": "say", "content": "test"}, None
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
            pid, "speech_speech", {"channel": "say", "content": "test"}, None
        )
        # message に typoed name は含まれる
        assert "speech_speech" in result.message
        # 近い候補 speech_speak がメッセージに含まれる (= fuzzy suggestion)
        assert "speech_speak" in result.message
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
