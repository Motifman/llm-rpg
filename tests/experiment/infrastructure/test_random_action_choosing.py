from __future__ import annotations

import random

from ai_rpg_world.experiment.infrastructure.random_action_choosing import (
    RANDOM_TEXT,
    CandidateTable,
    choose_random_call,
)

_TABLE = """【現在選べる対象引数】
- travel_to.destination:
    いまできる:
      (なし)
- interact.target:
    いまできる:
      "金庫"
- interact.how ("金庫"):
    いまできる:
      "番号を合わせて開ける"
    いまできない:
      "こじ開ける"（道具が無い）
- interact.details.code ("番号を合わせて開ける"): 番号を書く
- vote: いまできない（決めごとが無い）
※ 引数には「いまできる」の "" の中の文字をそのまま書く。
"""


def _tool(name: str, *arguments: str, required: tuple[str, ...] = (), details: bool = False) -> dict[str, object]:
    properties: dict[str, object] = {a: {"type": "string"} for a in arguments}
    if details:
        properties["details"] = {"type": "object"}
    return {
        "type": "function",
        "function": {"name": name, "parameters": {"properties": properties, "required": list(required)}},
    }


class TestCandidateTable:
    """CandidateTable.read が、新しい世界の【現在選べる対象引数】を、引数と親の候補ごとの「いまできる」に読み分けることを保証する。"""

    def test_available_values_are_read_under_their_parent(self) -> None:
        """「interact.how ("金庫")」の「いまできる」は、親を金庫とする行として読み、「いまできない」の候補は入らない。"""
        table = CandidateTable.read(_TABLE)

        row = table.row("interact", "how", ["金庫"])
        assert row is not None and row.available == ["番号を合わせて開ける"]

    def test_tool_unavailable_as_a_whole_is_read(self) -> None:
        """「- vote: いまできない（…）」は、行動ごと選べないツールとして読む。"""
        assert CandidateTable.read(_TABLE).unavailable_tools == frozenset({"vote"})

    def test_line_of_an_unknown_shape_is_kept_as_unreadable(self) -> None:
        """表の中に知らない形の行があると、読めなかった行として残す。"""
        table = CandidateTable.read(_TABLE.replace("※", "- travel_to destination?\n※"))

        assert table.unreadable_lines == ("- travel_to destination?",)


class TestChooseRandomCall:
    """choose_random_call が、候補のある引数は「いまできる」から選び、選べない行動を選ばないことを保証する。"""

    def test_safe_is_opened_with_a_written_code(self) -> None:
        """金庫を選ぶと、操作は「番号を合わせて開ける」になり、details.code に決まった文が書かれる。"""
        tools = [_tool("interact", "target", "how", required=("target",), details=True)]

        call = choose_random_call(random.Random(0), _TABLE, tools)

        assert call == {
            "name": "interact",
            "arguments": {"target": "金庫", "how": "番号を合わせて開ける", "details": {"code": RANDOM_TEXT}},
        }

    def test_tool_whose_required_argument_has_nothing_available_is_not_chosen(self) -> None:
        """行き先の「いまできる」が (なし) の travel_to と、行動ごと選べない vote は、どのシードでも選ばれない。"""
        tools = [_tool("travel_to", "destination", required=("destination",)), _tool("vote", "decision")]

        calls = [choose_random_call(random.Random(seed), _TABLE, tools) for seed in range(20)]

        assert calls == [None] * 20


class TestQuotedCandidates:
    """CandidateTable.read が、候補表が JSON の文字列で書いた候補を書き戻して読むことを保証する。"""

    def test_candidate_with_a_double_quote_is_read_back_unescaped(self) -> None:
        """「"錆びた" 鍵」が \\" で書かれていても、元の「"錆びた" 鍵」として読み、親の候補としても引ける。"""
        text = (
            "【現在選べる対象引数】\n"
            '- interact.target:\n    いまできる:\n      "\\"錆びた\\" 鍵"\n'
            '- interact.how ("\\"錆びた\\" 鍵"):\n    いまできる:\n      "回す"\n'
        )

        table = CandidateTable.read(text)

        row = table.row("interact", "target", [])
        assert row is not None and row.available == ['"錆びた" 鍵']
        how = table.row("interact", "how", ['"錆びた" 鍵'])
        assert how is not None and how.available == ["回す"]
        assert table.unreadable_lines == ()


class TestNestedDetails:
    """choose_random_call が、details の値の下に続く details の引数も、親を選んだあとに選ぶことを保証する。"""

    def test_detail_under_a_picked_detail_is_chosen(self) -> None:
        """details.lever で「左」を選ぶと、その下の details.force も選ぶ。"""
        text = (
            "【現在選べる対象引数】\n"
            '- interact.target:\n    いまできる:\n      "操作盤"\n'
            '- interact.details.lever ("操作盤"):\n    いまできる:\n      "左"\n'
            '- interact.details.force ("左"):\n    いまできる:\n      "強く"\n'
        )
        tools = [_tool("interact", "target", required=("target",), details=True)]

        call = choose_random_call(random.Random(0), text, tools)

        assert call is not None and call["arguments"]["details"] == {"lever": "左", "force": "強く"}
