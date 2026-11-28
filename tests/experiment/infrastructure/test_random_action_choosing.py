from __future__ import annotations

import random

from ai_rpg_world.experiment.infrastructure.random_action_choosing import (
    RANDOM_TEXT,
    CandidateTable,
    choose_random_call,
)

_PROMPT = """【現在地と周囲】
現在地: 鉱山会社の事務所
接続先:
  - "事務所と坑口の道" → "南の横坑口"（通行可）
オブジェクト:
  - "金庫" — 重い鉄の金庫。
同じ場所にいるプレイヤー:
  - "サヨ"

【選べる操作】
"金庫": "番号を合わせて金庫を開ける" (details.code に金庫の番号を書く), "こじ開ける"
"サヨ": "倒れている相手の持ち物を奪う" (details.item に奪う品の名前を書く)
"昇降機の籠": "籠に乗り込む" (set_sub_location)
vote "誰を残すか": "サヨ", "ゲン"
※ 行き先・人・品物・物は、【現在地と周囲】の "" の中の文字をそのまま引数に書く。
"""


def _tool(
    name: str,
    *arguments: str,
    required: tuple[str, ...] = (),
    details: bool = False,
    enums: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    properties: dict[str, object] = {
        a: {"type": "string", **({"enum": enums[a]} if enums and a in enums else {})} for a in arguments
    }
    if details:
        properties["details"] = {"type": "object"}
    return {
        "type": "function",
        "function": {"name": name, "parameters": {"properties": properties, "required": list(required)}},
    }


class TestCandidateTable:
    """CandidateTable.read が、【選べる操作】の行を、対象の名前ごと・ツールの名前ごとの候補に読み分けることを保証する。"""

    def test_operations_are_read_under_their_target_with_the_details_they_ask_for(self) -> None:
        """「"金庫": …」の行は、金庫の下の操作として読み、「(details.code に…)」から details のキー code を読む。"""
        table = CandidateTable.read(_PROMPT)

        row = table.below("interact", "金庫")
        assert row is not None
        assert [(listed.value, listed.asked_keys) for listed in row.listed] == [
            ("番号を合わせて金庫を開ける", ("code",)),
            ("こじ開ける", ()),
        ]

    def test_line_with_the_tool_name_last_gives_the_first_value_of_that_tool(self) -> None:
        """「"昇降機の籠": "籠に乗り込む" (set_sub_location)」は、set_sub_location の最初の値の候補として読み、籠を対象の行にしない。"""
        table = CandidateTable.read(_PROMPT)

        assert table.tool_values("set_sub_location") == ["籠に乗り込む"]
        assert table.below("interact", "昇降機の籠") is None

    def test_vote_line_gives_the_decision_and_its_choices(self) -> None:
        """「vote "誰を残すか": …」は、決めごとを vote の最初の値に、サヨ・ゲンをその下の値として読む。"""
        table = CandidateTable.read(_PROMPT)

        assert table.tool_values("vote") == ["誰を残すか"]
        row = table.below("vote", "誰を残すか")
        assert row is not None and [listed.value for listed in row.listed] == ["サヨ", "ゲン"]

    def test_quoted_names_before_the_table_are_read_as_scene_names(self) -> None:
        """【選べる操作】より前の "" の中の名前 (接続先・行き先・物・人) を、場面の名前として読む。"""
        assert CandidateTable.read(_PROMPT).scene_names == ("事務所と坑口の道", "南の横坑口", "金庫", "サヨ")

    def test_line_of_an_unknown_shape_is_kept_as_unreadable(self) -> None:
        """表の中に知らない形の行があると、読めなかった行として残す。"""
        table = CandidateTable.read(_PROMPT.replace("※", "金庫 開ける?\n※"))

        assert table.unreadable_lines == ("金庫 開ける?",)

    def test_the_shapes_the_being_writes_are_all_readable(self) -> None:
        """Being が書く 4 つの形の行と「なし」の行は、どれも読めなかった行にならない。"""
        assert CandidateTable.read(_PROMPT).unreadable_lines == ()
        assert CandidateTable.read("【選べる操作】\nなし\n※ 注記\n").unreadable_lines == ()

    def test_name_with_a_double_quote_is_read_back_unescaped(self) -> None:
        """「"錆びた" 鍵」が \\" で書かれていても、元の「"錆びた" 鍵」として読む。"""
        table = CandidateTable.read('【選べる操作】\n"\\"錆びた\\" 鍵": "回す"\n')

        row = table.below("interact", '"錆びた" 鍵')
        assert row is not None and [listed.value for listed in row.listed] == ["回す"]
        assert table.unreadable_lines == ()


class TestChooseRandomCall:
    """choose_random_call が、並ぶ候補はその行から、ほかの引数は場面の名前から選ぶことを保証する。"""

    def test_operation_under_the_chosen_target_comes_with_the_details_it_asks_for(self) -> None:
        """金庫を選んで「番号を合わせて金庫を開ける」を選ぶと、details.code に何かを書く。"""
        tools = [_tool("interact", "target", "how", required=("target",), details=True)]

        calls = [choose_random_call(random.Random(seed), _PROMPT, tools) for seed in range(40)]

        opened = [c for c in calls if c and c["arguments"].get("how") == "番号を合わせて金庫を開ける"]
        assert opened and all(
            c["arguments"]["target"] == "金庫" and "code" in c["arguments"]["details"] for c in opened
        )

    def test_fixed_values_are_chosen_from_the_enum(self) -> None:
        """話し方は、ツールの定義の enum の中から選ぶ。"""
        tools = [_tool("speak", "reach", required=("reach",), enums={"reach": ["叫ぶ"]})]

        call = choose_random_call(random.Random(0), _PROMPT, tools)

        assert call is not None and call["arguments"]["reach"] == "叫ぶ"

    def test_section_move_is_chosen_from_its_line(self) -> None:
        """set_sub_location の出入りは、籠の行の「籠に乗り込む」から選ぶ。"""
        tools = [_tool("set_sub_location", "move", required=("move",))]

        call = choose_random_call(random.Random(0), _PROMPT, tools)

        assert call == {"name": "set_sub_location", "arguments": {"move": "籠に乗り込む"}}

    def test_unlisted_required_argument_is_written_from_the_scene(self) -> None:
        """並ばない行き先は、場面の名前の中から書く。場面に名前が無ければ決まった文を書く。"""
        tools = [_tool("travel_to", "destination", required=("destination",))]

        call = choose_random_call(random.Random(0), _PROMPT, tools)
        bare = choose_random_call(random.Random(0), "【選べる操作】\nなし\n", tools)

        assert call is not None and call["arguments"]["destination"] in CandidateTable.read(_PROMPT).scene_names
        assert bare == {"name": "travel_to", "arguments": {"destination": RANDOM_TEXT}}
