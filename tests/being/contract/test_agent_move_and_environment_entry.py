"""エージェントの 1 手 (``AgentMove``) と環境に入るときの取り決め (``EnvironmentEntry``) の欄の決まりを保証する。"""

from __future__ import annotations

import copy
import pickle
from datetime import datetime

import pytest

from ai_rpg_world.being.contract import (
    AgentMove,
    ContractViolation,
    EnvironmentEntry,
    Introduction,
)


class TestAgentMove:
    """エージェントの 1 手が「何をしたか」だけを持ち、呼び出しの ID で結果と結べることを保証する。"""

    def test_move_keeps_call_id_name_arguments_and_subjective_fields(self) -> None:
        """呼び出しの ID・名前・引数・予期・内心を渡すと、そのまま読める。"""
        move = AgentMove(
            call_id="call-1",
            tool_name="travel_to",
            arguments={"destination_label": "通信室"},
            expectation="通信室に着く",
            inner_thought="まず点検に行く",
        )

        assert move.call_id == "call-1"
        assert move.tool_name == "travel_to"
        assert dict(move.arguments) == {"destination_label": "通信室"}
        assert move.expectation == "通信室に着く"
        assert move.inner_thought == "まず点検に行く"

    def test_subjective_fields_are_optional(self) -> None:
        """予期・内心を省くと None になる。"""
        move = AgentMove(call_id="call-1", tool_name="wait", arguments={})

        assert (move.expectation, move.inner_thought) == (None, None)

    def test_arguments_are_copied_and_read_only(self) -> None:
        """渡した辞書を後から書き換えても 1 手の引数は変わらず、1 手の引数は書き換えられない。"""
        source = {"destination_label": "通信室"}
        move = AgentMove(call_id="call-1", tool_name="travel_to", arguments=source)
        source["destination_label"] = "倉庫"

        assert move.arguments["destination_label"] == "通信室"
        with pytest.raises(TypeError):
            move.arguments["destination_label"] = "倉庫"  # type: ignore[index]

    def test_nested_argument_values_are_frozen(self) -> None:
        """入れ子の配列と対応表も書き換えられない形で持ち、渡した側の後からの変更は届かない。"""
        gives = [{"item_label": "貝", "count": 2}]
        move = AgentMove(call_id="call-1", tool_name="give_item", arguments={"gives": gives})
        gives[0]["count"] = 9

        frozen = move.arguments["gives"]
        assert isinstance(frozen, tuple)
        assert dict(frozen[0]) == {"item_label": "貝", "count": 2}  # type: ignore[call-overload]
        with pytest.raises(TypeError):
            frozen[0]["count"] = 9  # type: ignore[index]

    @pytest.mark.parametrize("value", [datetime(2026, 1, 1), object(), float("nan")])
    def test_non_json_argument_value_is_rejected(self, value: object) -> None:
        """引数の値に JSON で表せない値 (日時・任意のオブジェクト・NaN) を渡すと拒む。"""
        with pytest.raises(ContractViolation):
            AgentMove(call_id="call-1", tool_name="wait", arguments={"x": value})

    def test_move_is_hashable_copyable_and_picklable(self) -> None:
        """1 手はハッシュでき、複製と pickle の往復で等しいまま残る。"""
        move = AgentMove(
            call_id="call-1", tool_name="give_item", arguments={"gives": [{"item_label": "貝"}]}
        )

        assert hash(move) == hash(copy.deepcopy(move))
        assert pickle.loads(pickle.dumps(move)) == move

    @pytest.mark.parametrize("field", ["call_id", "tool_name"])
    def test_blank_identity_is_rejected(self, field: str) -> None:
        """呼び出しの ID か名前が空なら拒む。"""
        values = {"call_id": "call-1", "tool_name": "wait", field: " "}

        with pytest.raises(ContractViolation):
            AgentMove(arguments={}, **values)

    @pytest.mark.parametrize("field", ["expectation", "inner_thought"])
    def test_blank_subjective_field_is_rejected(self, field: str) -> None:
        """予期・内心に空文字を渡すと拒む。書かないときは省く。"""
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


class TestIntroductions:
    """入るときの紹介が、名前と関係の注記を持ち、紹介しない環境では空になることを保証する。"""

    def test_entry_without_introductions_introduces_nobody(self) -> None:
        """introductions を省くと、誰も紹介されない空の tuple になる。"""
        entry = EnvironmentEntry(environment_name="山村", self_name="リオ")

        assert entry.introductions == ()

    def test_introductions_keep_names_and_relation_notes_in_order(self) -> None:
        """紹介は渡した順に、名前と関係の注記 (無ければ None) を保つ。"""
        entry = EnvironmentEntry(
            environment_name="山村",
            self_name="リオ",
            introductions=[
                Introduction(name="ノア", relation_note="あなたと同じ側"),
                Introduction(name="カイ"),
            ],
        )

        assert entry.introductions == (
            Introduction(name="ノア", relation_note="あなたと同じ側"),
            Introduction(name="カイ", relation_note=None),
        )

    def test_blank_name_or_note_is_rejected(self) -> None:
        """紹介の名前が空、または関係の注記が空文字なら拒む。"""
        with pytest.raises(ContractViolation):
            Introduction(name=" ")
        with pytest.raises(ContractViolation):
            Introduction(name="ノア", relation_note="")

    def test_introducing_oneself_or_the_same_person_twice_is_rejected(self) -> None:
        """本人を紹介したり、同じ名前を 2 回紹介したりすると拒む。"""
        with pytest.raises(ContractViolation):
            EnvironmentEntry(
                environment_name="山村", self_name="リオ",
                introductions=[Introduction(name="リオ")],
            )
        with pytest.raises(ContractViolation):
            EnvironmentEntry(
                environment_name="山村", self_name="リオ",
                introductions=[Introduction(name="ノア"), Introduction(name="ノア")],
            )

    def test_non_introduction_items_are_rejected(self) -> None:
        """紹介に Introduction 以外 (名前の文字列など) を混ぜると拒む。"""
        with pytest.raises(ContractViolation):
            EnvironmentEntry(
                environment_name="山村", self_name="リオ", introductions=["ノア"],
            )
