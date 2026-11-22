from __future__ import annotations

import pytest

from ai_rpg_world.being.application.action_tools import ActionTools
from ai_rpg_world.being.contract import (
    ActionChoice,
    ActionChoices,
    ArgumentOutline,
    Candidate,
    FreeText,
    OfferedBeingTools,
    PersonInText,
    PersonPlaceholderValue,
    PickOne,
    TextWithPeople,
    UnavailableAction,
    UnidentifiedPerson,
)

SAYO = PersonInText(handle=2, appearance="綿入れを着込んだ若い娘", visible_name="サヨ")
SHADOW_A = PersonInText(handle=7, appearance="煤けた上着の男", visible_name=None)
SHADOW_B = PersonInText(handle=9, appearance="煤けた上着の男", visible_name=None)
SAY_INLINE = ArgumentOutline(name="say_inline", label="この行動をしながら、同じ場所の人にかける一言 (任意)")
TOOLS = OfferedBeingTools(inner_thought="inner_thought")
WITH_MEMORY = OfferedBeingTools(
    inner_thought="inner_thought", memo="memo", episode_recall="episode_recall", episode_index_shown=True
)


def _name_for(person: PersonPlaceholderValue) -> str:
    if isinstance(person, UnidentifiedPerson):
        return "誰か"
    return person.visible_name or person.appearance


def _travel(*destinations: str) -> ActionChoice:
    return ActionChoice(
        name="travel_to",
        label="行く",
        outline=(ArgumentOutline(name="destination", label="行き先", required=True), SAY_INLINE),
        values=(
            PickOne(name="destination", label="行き先", candidates=tuple(Candidate(label=d) for d in destinations)),
        ),
    )


def _speak(*listeners: PersonInText) -> ActionChoice:
    content = FreeText(name="content", label="中身")
    whisper = PickOne(
        name="to", label="相手", candidates=tuple(Candidate(label=p, values=(content,)) for p in listeners)
    )
    reaches = [Candidate(label="ふつうの声で話す", values=(content,))]
    if listeners:
        reaches.append(Candidate(label="ささやく", values=(whisper,)))
    return ActionChoice(
        name="speak",
        label="話す",
        outline=(
            ArgumentOutline(name="reach", label="届け方", required=True),
            ArgumentOutline(name="to", label="相手"),
            ArgumentOutline(name="content", label="中身"),
        ),
        values=(PickOne(name="reach", label="届け方", candidates=tuple(reaches)),),
    )


def _interact(*targets: Candidate) -> ActionChoice:
    return ActionChoice(
        name="interact",
        label="操作する",
        outline=(
            ArgumentOutline(name="target", label="相手", required=True),
            ArgumentOutline(name="how", label="操作"),
            SAY_INLINE,
        ),
        takes_details=True,
        values=(PickOne(name="target", label="相手", candidates=targets),),
    )


SAFE = Candidate(
    label="金庫",
    values=(
        PickOne(
            name="how",
            label="操作",
            candidates=(Candidate(label="番号を合わせて開ける", values=(FreeText(name="code", label="番号"),)),),
        ),
    ),
)


def _gen_in_the_office() -> ActionChoices:
    return ActionChoices((_travel("井戸", "鍛冶場", "南の横坑口"), _speak(SAYO), _interact(SAFE)))


def _tools(choices: ActionChoices, being_tools: OfferedBeingTools = TOOLS) -> ActionTools:
    return ActionTools(choices, being_tools, _name_for, recall_limit=3)


def _table(choices: ActionChoices) -> list[str]:
    text = _tools(choices).candidate_table().text
    assert isinstance(text, str)
    return text.split("\n")


class TestActionToolDefinitions:
    """ActionTools.definitions が、行動の種類ごとに 1 つのツールを、候補によらない形で組むことを保証する。"""

    def test_gen_gets_one_tool_per_kind_of_action(self) -> None:
        """事務所のゲンに「行く」「話す」「操作する」の選択肢を渡すと、その 3 つのツールがこの順に並ぶ。"""
        definitions = _tools(_gen_in_the_office()).definitions()

        assert [d["function"]["name"] for d in definitions] == ["travel_to", "speak", "interact"]

    def test_definitions_stay_the_same_after_moving_to_the_well(self) -> None:
        """井戸に移って行き先・話し相手・操作できる物が変わっても、ツールの定義は 1 文字も変わらない。"""
        at_the_well = ActionChoices((_travel("事務所"), _speak(), _interact()))

        assert _tools(at_the_well).definitions() == _tools(_gen_in_the_office()).definitions()

    def test_interact_takes_the_path_on_top_and_declared_arguments_in_details(self) -> None:
        """interact は、道筋 (target・how) と say_inline を上の段に、操作の宣言の引数を details に受け、相手と独白を必須にする。"""
        [interact] = _tools(ActionChoices((_interact(SAFE),))).definitions()

        parameters = interact["function"]["parameters"]
        assert list(parameters["properties"]) == ["target", "how", "say_inline", "details", "inner_thought"]
        assert parameters["required"] == ["target", "inner_thought"]

    def test_optional_say_inline_is_not_required(self) -> None:
        """見取り図に say_inline しか無い待つは、say_inline を必須にせず、独白だけを必須にする。"""
        wait = ActionChoice(name="wait", label="待つ", outline=(SAY_INLINE,))

        [definition] = _tools(ActionChoices((wait,))).definitions()

        assert definition["function"]["parameters"]["required"] == ["inner_thought"]

    def test_candidates_are_not_written_into_the_definition(self) -> None:
        """ツールの説明と引数には、このターンの候補 (金庫) を書かない。"""
        [interact] = _tools(ActionChoices((_interact(SAFE),))).definitions()

        assert "金庫" not in str(interact)

    def test_inner_thought_is_left_out_when_not_offered(self) -> None:
        """独白の引数を環境が出していなければ、ツールに独白の引数を付けない。"""
        [wait] = _tools(ActionChoices((ActionChoice(name="wait", label="待つ"),)), OfferedBeingTools()).definitions()

        assert wait["function"]["parameters"] == {"type": "object", "properties": {}, "required": []}

    @pytest.mark.parametrize("reserved", ["details", "inner_thought", "memo"])
    def test_outline_name_reserved_by_the_being_is_rejected(self, reserved: str) -> None:
        """見取り図に Being の使う引数の名前 (details・独白・メモ) があると、ツールの引数が重なるので ValueError を投げる。"""
        choice = ActionChoice(name="wait", label="待つ", outline=(ArgumentOutline(name=reserved, label="細かいこと"),))

        with pytest.raises(ValueError, match=reserved):
            _tools(ActionChoices((choice,)), WITH_MEMORY).definitions()

    def test_memo_is_added_to_every_action_tool_but_not_required(self) -> None:
        """メモの引数を環境が出していれば、どの行動のツールにも memo を付け、必須にはしない。"""
        definitions = _tools(_gen_in_the_office(), WITH_MEMORY).definitions()

        actions = [d["function"] for d in definitions if d["function"]["name"] != "episode_recall"]
        assert all("memo" in a["parameters"]["properties"] for a in actions)
        assert all("memo" not in a["parameters"]["required"] for a in actions)

    @pytest.mark.parametrize(
        ("index_shown", "sources"), [(True, ["self", "heard", "episode"]), (False, ["self", "heard"])]
    )
    def test_memo_offers_episode_as_a_source_only_when_the_index_is_shown(
        self, index_shown: bool, sources: list[str]
    ) -> None:
        """メモの出どころに episode を出すのは、呼び名の載る【思い出せる出来事】を出しているときだけ。"""
        being_tools = OfferedBeingTools(memo="memo", episode_index_shown=index_shown)

        [wait] = _tools(ActionChoices((ActionChoice(name="wait", label="待つ"),)), being_tools).definitions()

        assert wait["function"]["parameters"]["properties"]["memo"]["items"]["properties"]["source"]["enum"] == sources

    def test_recall_tool_follows_the_action_tools_when_offered(self) -> None:
        """思い出すツールを環境が出していれば、行動のツールの後ろに並べ、一度に思い出せる件数を上限にする。"""
        definitions = _tools(_gen_in_the_office(), WITH_MEMORY).definitions()

        assert [d["function"]["name"] for d in definitions] == ["travel_to", "speak", "interact", "episode_recall"]
        assert definitions[-1]["function"]["parameters"]["properties"]["handles"]["maxItems"] == 3

    def test_recall_tool_is_left_out_when_not_offered(self) -> None:
        """思い出すツールを環境が出していなければ、行動のツールだけが並ぶ。"""
        assert _tools(_gen_in_the_office()).tool_names() == ("travel_to", "speak", "interact")


class TestCandidateTable:
    """ActionTools.candidate_table が、このターンの候補と、いまはできないことを場面の文にすることを保証する。"""

    def test_destinations_without_further_values_share_one_line(self) -> None:
        """続けて決める値の無い候補 (行き先) は、引数の名前のあとに 1 行で並ぶ。"""
        assert _table(ActionChoices((_travel("井戸", "鍛冶場", "南の横坑口"),))) == [
            "travel_to（行く）",
            "- destination: 井戸 / 鍛冶場 / 南の横坑口",
        ]

    def test_path_to_the_safe_shows_the_declared_argument_under_details(self) -> None:
        """金庫を番号で開ける道筋は、target・how を上の段の名前で、番号を details.code で示す 1 行になる。"""
        assert _table(ActionChoices((_interact(SAFE),)))[1:] == [
            "- target: 金庫, how: 番号を合わせて開ける, details.code: （番号を書く）"
        ]

    def test_whisper_to_sayo_names_her_by_her_visible_name(self) -> None:
        """ささやく相手のサヨは、人の印ではなく見えている名前で出る。"""
        assert _table(ActionChoices((_speak(SAYO),)))[1:] == [
            "- reach: ふつうの声で話す, content: （中身を書く）",
            "- reach: ささやく, to: サヨ, content: （中身を書く）",
        ]

    def test_people_who_look_alike_are_numbered(self) -> None:
        """見分けのつかない同じ見た目の 2 人は、「(1)」「(2)」を添えて別々に出る。"""
        assert _table(ActionChoices((_speak(SHADOW_A, SHADOW_B),)))[2:] == [
            "- reach: ささやく, to: 煤けた上着の男 (1), content: （中身を書く）",
            "- reach: ささやく, to: 煤けた上着の男 (2), content: （中身を書く）",
        ]

    def test_items_with_the_same_name_show_their_count(self) -> None:
        """同じ名前の品物は、数を添えて出る。"""
        drop = ActionChoice(
            name="drop_item",
            label="置く",
            outline=(ArgumentOutline(name="item", label="品物", required=True),),
            values=(PickOne(name="item", label="品物", candidates=(Candidate(label="ランプの油", count=3),)),),
        )

        assert _table(ActionChoices((drop,)))[1:] == ["- item: ランプの油 ×3"]

    def test_unavailable_lamp_is_shown_with_its_reason(self) -> None:
        """ランプを手に持つことがいまはできないなら、候補が無いことと、ランプと理由の行が出る。"""
        hold = ActionChoice(
            name="hold_item",
            label="手に持つ",
            outline=(ArgumentOutline(name="item", label="品物", required=True),),
            values=(PickOne(name="item", label="品物", candidates=()),),
            unavailable=(UnavailableAction(picked=("ランプ",), reason="両手がふさがっている"),),
        )

        assert _table(ActionChoices((hold,))) == [
            "hold_item（手に持つ）",
            "- いまは候補が無い",
            "- いまはできない: ランプ — 両手がふさがっている",
        ]

    def test_whole_action_unavailable_shows_only_the_reason(self) -> None:
        """行動ごといまはできないなら、理由の行だけが出る。"""
        listen = ActionChoice(
            name="listen", label="耳を澄ます", unavailable=(UnavailableAction(picked=(), reason="手が離せない"),)
        )

        assert _table(ActionChoices((listen,))) == ["listen（耳を澄ます）", "- いまはできない: 手が離せない"]

    def test_reason_naming_people_uses_the_same_names(self) -> None:
        """理由の文の人の穴は、候補と同じ呼び方で埋まり、見分けられない人は呼び方の部品の言い方で出る。"""
        tend = ActionChoice(
            name="tend_to_player",
            label="介抱する",
            outline=(ArgumentOutline(name="target", label="相手", required=True),),
            values=(PickOne(name="target", label="相手", candidates=()),),
            unavailable=(
                UnavailableAction(
                    picked=(SAYO,),
                    reason=TextWithPeople(
                        template="{sayo}は{other}と話している", people={"sayo": SAYO, "other": UnidentifiedPerson()}
                    ),
                ),
            ),
        )

        assert _table(ActionChoices((tend,)))[2] == "- いまはできない: サヨ — サヨは誰かと話している"

    def test_action_without_values_says_there_is_nothing_to_pick(self) -> None:
        """値の無い行動は、選ぶ値が無いことを 1 行で示す。"""
        assert _table(ActionChoices((ActionChoice(name="wait", label="待つ"),))) == ["wait（待つ）", "- 選ぶ値は無い"]


class TestMoveFrom:
    """ActionTools.move_from が、LLM のツールの呼び出しを、世界に返す AgentMove に変える決まりを保証する。"""

    def test_unknown_tool_name_gives_no_move(self) -> None:
        """出していないツールの名前なら None を返す。"""
        assert _tools(_gen_in_the_office()).move_from(call_id="c1", tool_name="gather", arguments={}) is None

    def test_top_level_wins_over_the_same_name_in_details(self) -> None:
        """details の中に上の段と同じ名前があれば、上の段の値を使う。"""
        move = _tools(ActionChoices((_interact(SAFE),))).move_from(
            call_id="c1", tool_name="interact", arguments={"target": "金庫", "details": {"target": "机", "code": "1"}}
        )

        assert move is not None and dict(move.arguments) == {"target": "金庫", "code": "1"}

    def test_details_of_a_choice_without_details_is_kept_as_it_is(self) -> None:
        """details を受けない選択肢に details が来ても、外さずにそのまま世界に渡す。"""
        move = _tools(_gen_in_the_office()).move_from(
            call_id="c1", tool_name="travel_to", arguments={"destination": "井戸", "details": {"x": "1"}}
        )

        assert move is not None and dict(move.arguments) == {"destination": "井戸", "details": {"x": "1"}}

    def test_name_not_called_this_turn_stays_text(self) -> None:
        """このターンに出ていない呼び方 (ミオ) は、人の印に戻さず文字のまま渡す。"""
        move = _tools(_gen_in_the_office()).move_from(
            call_id="c1", tool_name="speak", arguments={"reach": "ささやく", "to": "ミオ", "content": "やあ"}
        )

        assert move is not None and move.arguments["to"] == "ミオ"

    def test_memo_is_not_passed_to_the_world(self) -> None:
        """行動と一緒に書いたメモは Being が書くので、世界に渡す AgentMove の引数には残さない。"""
        move = _tools(_gen_in_the_office(), WITH_MEMORY).move_from(
            call_id="c1",
            tool_name="travel_to",
            arguments={"destination": "井戸", "memo": [{"do": "add", "kind": "todo", "text": "水を汲む"}]},
        )

        assert move is not None and dict(move.arguments) == {"destination": "井戸"}

    def test_recall_tool_gives_no_move(self) -> None:
        """思い出すツールは世界の行為ではないので、AgentMove にしない。"""
        tools = _tools(_gen_in_the_office(), WITH_MEMORY)

        assert tools.move_from(call_id="c1", tool_name="episode_recall", arguments={"handles": ["ep_1"]}) is None

    def test_blank_inner_thought_is_dropped(self) -> None:
        """独白が空白だけなら、AgentMove の独白は None になり、引数にも残らない。"""
        move = _tools(_gen_in_the_office()).move_from(
            call_id="c1", tool_name="travel_to", arguments={"destination": "井戸", "inner_thought": "  "}
        )

        assert move is not None and move.inner_thought is None and "inner_thought" not in move.arguments


class TestActionHeading:
    """ActionTools.action_heading が、選んだ行動を候補表と同じ並べ方の見出しにすることを保証する。"""

    def test_safe_with_a_code_reads_picks_then_written_values(self) -> None:
        """金庫を番号で開けると、見出し・選んだ候補を「 / 」でつないだもの・(書いた値の見出し: 値) の順になる。"""
        heading = _tools(ActionChoices((_interact(SAFE),))).action_heading(
            "interact", {"target": "金庫", "how": "番号を合わせて開ける", "details": {"code": "1907"}}
        )

        assert heading == "操作する: 金庫 / 番号を合わせて開ける (番号: 1907)"

    def test_action_without_values_is_its_label(self) -> None:
        """選ぶ値の無い行動は、見出しだけになる。"""
        heading = _tools(ActionChoices((ActionChoice(name="listen", label="耳を澄ます"),))).action_heading("listen", {})

        assert heading == "耳を澄ます"

    def test_whisper_names_the_listener_as_the_being_calls_her(self) -> None:
        """サヨにささやくと、相手は呼び方のまま並び、中身は括弧に入る。"""
        heading = _tools(_gen_in_the_office()).action_heading(
            "speak", {"reach": "ささやく", "to": "サヨ", "content": "鍵はどこ?"}
        )

        assert heading == "話す: ささやく / サヨ (中身: 鍵はどこ?)"

    def test_inline_speech_is_left_out(self) -> None:
        """行動しながらの一言 (say_inline) は、選択肢の値ではないので見出しに出さない。"""
        heading = _tools(_gen_in_the_office()).action_heading(
            "travel_to", {"destination": "井戸", "say_inline": "行くぞ"}
        )

        assert heading == "行く: 井戸"

    def test_value_that_is_not_a_candidate_is_shown_as_written(self) -> None:
        """候補に無い値を選んでも、書いたとおりに見出しへ並べる。断るかどうかは世界が決める。"""
        heading = _tools(_gen_in_the_office()).action_heading("travel_to", {"destination": "天守閣"})

        assert heading == "行く: 天守閣"

    def test_tool_that_was_not_offered_has_no_heading(self) -> None:
        """出していないツールの名前なら None を返す。"""
        assert _tools(_gen_in_the_office()).action_heading("gather", {}) is None
