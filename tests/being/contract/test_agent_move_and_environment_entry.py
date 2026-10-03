"""エージェントの 1 手 (``AgentMove``) と環境に入るときの取り決め (``EnvironmentEntry``) の欄の決まりを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import AgentMove, ContractViolation, EnvironmentEntry


class TestAgentMove:
    """エージェントの 1 手が「何をしたか」だけを持ち、呼び出しの ID で結果と結べることを保証する。"""

    def test_move_keeps_call_id_name_arguments_and_subjective_fields(self) -> None:
        """呼び出しの ID・名前・引数・予期・内心・目的の更新を渡すと、そのまま読める。"""
        move = AgentMove(
            call_id="call-1",
            tool_name="travel_to",
            arguments={"destination_label": "通信室"},
            expectation="通信室に着く",
            inner_thought="まず点検に行く",
            goal_update="観測室の計器を直す",
        )

        assert move.call_id == "call-1"
        assert move.tool_name == "travel_to"
        assert dict(move.arguments) == {"destination_label": "通信室"}
        assert move.expectation == "通信室に着く"
        assert move.inner_thought == "まず点検に行く"
        assert move.goal_update == "観測室の計器を直す"

    def test_subjective_fields_are_optional(self) -> None:
        """予期・内心・目的の更新を省くと None になる。"""
        move = AgentMove(call_id="call-1", tool_name="wait", arguments={})

        assert (move.expectation, move.inner_thought, move.goal_update) == (None, None, None)

    def test_arguments_are_copied_and_read_only(self) -> None:
        """渡した辞書を後から書き換えても 1 手の引数は変わらず、1 手の引数は書き換えられない。"""
        source = {"destination_label": "通信室"}
        move = AgentMove(call_id="call-1", tool_name="travel_to", arguments=source)
        source["destination_label"] = "倉庫"

        assert move.arguments["destination_label"] == "通信室"
        with pytest.raises(TypeError):
            move.arguments["destination_label"] = "倉庫"  # type: ignore[index]

    @pytest.mark.parametrize("field", ["call_id", "tool_name"])
    def test_blank_identity_is_rejected(self, field: str) -> None:
        """呼び出しの ID か名前が空なら拒む。"""
        values = {"call_id": "call-1", "tool_name": "wait", field: " "}

        with pytest.raises(ContractViolation):
            AgentMove(arguments={}, **values)

    @pytest.mark.parametrize("field", ["expectation", "inner_thought", "goal_update"])
    def test_blank_subjective_field_is_rejected(self, field: str) -> None:
        """予期・内心・目的の更新に空文字を渡すと拒む。書かないときは省く。"""
        with pytest.raises(ContractViolation):
            AgentMove(call_id="call-1", tool_name="wait", arguments={}, **{field: ""})

    def test_argument_names_must_be_non_blank_str(self) -> None:
        """引数名が空文字なら拒む。"""
        with pytest.raises(ContractViolation):
            AgentMove(call_id="call-1", tool_name="wait", arguments={"": "x"})


class TestEnvironmentEntry:
    """環境に入るときの取り決めが、環境の名前・本人の名前・課す目的を持つことを保証する。"""

    def test_entry_keeps_names_and_imposed_goal(self) -> None:
        """環境の名前・本人の名前・課す目的を渡すと、そのまま読める。"""
        entry = EnvironmentEntry(
            environment_name="遭難の島",
            self_name="リオ",
            imposed_goal="山頂の狼煙台に火を灯す",
        )

        assert entry.environment_name == "遭難の島"
        assert entry.self_name == "リオ"
        assert entry.imposed_goal == "山頂の狼煙台に火を灯す"

    def test_imposed_goal_is_optional(self) -> None:
        """目的を課さない環境では imposed_goal を省け、None になる。"""
        entry = EnvironmentEntry(environment_name="返信だけの環境", self_name="リオ")

        assert entry.imposed_goal is None

    @pytest.mark.parametrize("field", ["environment_name", "self_name"])
    def test_blank_name_is_rejected(self, field: str) -> None:
        """環境の名前か本人の名前が空なら拒む。"""
        values = {"environment_name": "遭難の島", "self_name": "リオ", field: ""}

        with pytest.raises(ContractViolation):
            EnvironmentEntry(**values)
