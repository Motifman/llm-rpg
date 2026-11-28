from __future__ import annotations

from collections.abc import Mapping

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
        description="説明。",
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
        description="説明。",
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
        description="説明。",
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


NOTE = (
    '※ 引数には「いまできる」の "" の中の文字をそのまま書く。「いまできない」は、（）の理由があるあいだは選んでも断られる。'
    "一覧にあることは操作の成功を保証しない。現在の状態や前提条件によって失敗する場合がある。"
)


def _table(choices: ActionChoices) -> list[str]:
    table = _tools(choices).candidate_table()
    assert table is not None and table.heading == "現在選べる対象引数"
    assert isinstance(table.text, str)
    return table.text.split("\n")


class TestActionToolDefinitions:
    """ActionTools.definitions が、行動の種類ごとに 1 つのツールを、候補によらない形で組むことを保証する。"""

    def test_gen_gets_one_tool_per_kind_of_action(self) -> None:
        """事務所のゲンに「行く」「話す」「操作する」の選択肢を渡すと、その 3 つのツールがこの順に並ぶ。"""
        definitions = _tools(_gen_in_the_office()).definitions()

        assert [d["function"]["name"] for d in definitions] == ["travel_to", "speak", "interact"]

    def test_description_says_to_copy_what_can_be_done_now(self) -> None:
        """ツールの説明は、世界が渡した行動の説明のあとに「候補のある引数には【現在選べる対象引数】の「いまできる」の文字をそのまま書く。」が続く。"""
        [travel] = _tools(ActionChoices((_travel("井戸"),))).definitions()

        assert travel["function"]["description"] == (
            "説明。候補のある引数には【現在選べる対象引数】の「いまできる」の文字をそのまま書く。"
        )

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
        wait = ActionChoice(description="説明。", name="wait", label="待つ", outline=(SAY_INLINE,))

        [definition] = _tools(ActionChoices((wait,))).definitions()

        assert definition["function"]["parameters"]["required"] == ["inner_thought"]

    def test_max_length_of_the_outline_limits_the_argument(self) -> None:
        """見取り図が長さの上限 (200) を持つ引数は、ツールの定義の maxLength になり、持たない引数には付かない。"""
        wait = ActionChoice(
            description="説明。",
            name="wait",
            label="待つ",
            outline=(
                ArgumentOutline(name="say_inline", label="一言", max_length=200),
                ArgumentOutline(name="note", label="覚え"),
            ),
        )

        [definition] = _tools(ActionChoices((wait,))).definitions()

        properties = definition["function"]["parameters"]["properties"]
        assert properties["say_inline"] == {"type": "string", "description": "一言", "maxLength": 200}
        assert "maxLength" not in properties["note"]

    def test_candidates_are_not_written_into_the_definition(self) -> None:
        """ツールの説明と引数には、このターンの候補 (金庫) を書かない。"""
        [interact] = _tools(ActionChoices((_interact(SAFE),))).definitions()

        assert "金庫" not in str(interact)

    def test_inner_thought_is_left_out_when_not_offered(self) -> None:
        """独白の引数を環境が出していなければ、ツールに独白の引数を付けない。"""
        [wait] = _tools(
            ActionChoices((ActionChoice(description="説明。", name="wait", label="待つ"),)), OfferedBeingTools()
        ).definitions()

        assert wait["function"]["parameters"] == {"type": "object", "properties": {}, "required": []}

    @pytest.mark.parametrize("reserved", ["details", "inner_thought", "memo"])
    def test_outline_name_reserved_by_the_being_is_rejected(self, reserved: str) -> None:
        """見取り図に Being の使う引数の名前 (details・独白・メモ) があると、ツールの引数が重なるので ValueError を投げる。"""
        choice = ActionChoice(
            description="説明。",
            name="wait",
            label="待つ",
            outline=(ArgumentOutline(name=reserved, label="細かいこと"),),
        )

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

        [wait] = _tools(
            ActionChoices((ActionChoice(description="説明。", name="wait", label="待つ"),)), being_tools
        ).definitions()

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
    """ActionTools.candidate_table が、このターンの候補と、いまはできない候補を理由つきで、引数ごとの段の形で場面の文にすることを保証する。"""

    def test_destinations_are_listed_one_per_line_under_what_can_be_done_now(self) -> None:
        """行き先は「- ツールの名前.引数の名前:」の下の「いまできる:」に 1 つ 1 行で並び、最後に注意書きが付く。"""
        assert _table(ActionChoices((_travel("井戸", "鍛冶場", "南の横坑口"),))) == [
            "- travel_to.destination:",
            "    いまできる:",
            '      "井戸"',
            '      "鍛冶場"',
            '      "南の横坑口"',
            NOTE,
        ]

    def test_value_chosen_under_a_candidate_names_that_candidate(self) -> None:
        """金庫の下で選ぶ操作は、どの候補の下かを括弧に添えた見出しになる。番号の値は何を書くか (writes) を持たないので、表に出ない。"""
        assert _table(ActionChoices((_interact(SAFE),)))[:-1] == [
            "- interact.target:",
            "    いまできる:",
            '      "金庫"',
            '- interact.how ("金庫"):',
            "    いまできる:",
            '      "番号を合わせて開ける"',
        ]

    def test_unavailable_operation_is_listed_with_its_reason_under_the_same_heading(self) -> None:
        """金庫の「開ける」がいまできないなら、金庫の操作の見出しの「いまできない:」に、理由を全角の丸括弧に入れて出る。理由の句点は外す。"""
        locked = UnavailableAction(picked=("金庫", "開ける"), argument="how", reason="鍵が掛かっている。")
        interact = _interact(SAFE)
        choice = ActionChoice(
            description="説明。",
            name=interact.name,
            label=interact.label,
            outline=interact.outline,
            takes_details=True,
            values=interact.values,
            unavailable=(locked,),
        )

        assert _table(ActionChoices((choice,)))[3:-1] == [
            '- interact.how ("金庫"):',
            "    いまできる:",
            '      "番号を合わせて開ける"',
            "    いまできない:",
            '      "開ける"（鍵が掛かっている）',
        ]

    def test_unavailable_destination_follows_those_that_can_be_reached(self) -> None:
        """通れない行き先は、行き先の見出しの「いまできない:」に出る。"""
        travel = _travel("井戸")
        choice = ActionChoice(
            description="説明。",
            name=travel.name,
            label=travel.label,
            outline=travel.outline,
            values=travel.values,
            unavailable=(
                UnavailableAction(
                    picked=("北の竪坑の底",), argument="destination", reason="梯子が外れていて下りられない"
                ),
            ),
        )

        assert _table(ActionChoices((choice,))) == [
            "- travel_to.destination:",
            "    いまできる:",
            '      "井戸"',
            "    いまできない:",
            '      "北の竪坑の底"（梯子が外れていて下りられない）',
            NOTE,
        ]

    def test_operations_of_a_target_with_nothing_doable_get_their_own_heading(self) -> None:
        """物置の操作がどれもいまできず物置が候補に並ばなくても、物置の操作の見出しを立て、いまできるものは「(なし)」と出す。"""
        interact = _interact(SAFE)
        choice = ActionChoice(
            description="説明。",
            name=interact.name,
            label=interact.label,
            outline=interact.outline,
            takes_details=True,
            values=interact.values,
            unavailable=(UnavailableAction(picked=("物置", "開ける"), argument="how", reason="錠前が錆びている"),),
        )

        assert _table(ActionChoices((choice,)))[6:-1] == [
            '- interact.how ("物置"):',
            "    いまできる:",
            "      (なし)",
            "    いまできない:",
            '      "開ける"（錠前が錆びている）',
        ]

    def test_free_text_with_writes_says_what_to_write_under_its_candidate(self) -> None:
        """何を書くか (金庫の番号) を持つ自由に書く値は、段の形にせず「- interact.details.code ("番号を合わせて開ける"): 金庫の番号を書く」の 1 行で出る。"""
        guided = Candidate(
            label="金庫",
            values=(
                PickOne(
                    name="how",
                    label="操作",
                    candidates=(
                        Candidate(
                            label="番号を合わせて開ける",
                            values=(FreeText(name="code", label="code", writes="金庫の番号"),),
                        ),
                    ),
                ),
            ),
        )

        assert _table(ActionChoices((_interact(guided),)))[-2] == (
            '- interact.details.code ("番号を合わせて開ける"): 金庫の番号を書く'
        )

    def test_speech_content_without_writes_stays_out_of_the_table(self) -> None:
        """何を書くかを持たない話す中身 (content) は、ツールの引数の説明で分かるので、表に出ない。"""
        assert all("content" not in line for line in _table(ActionChoices((_speak(SAYO),))))

    def test_whisper_to_sayo_names_her_by_her_visible_name(self) -> None:
        """ささやく相手のサヨは、人の印ではなく見えている名前で、ささやくの下の見出しに出る。"""
        assert _table(ActionChoices((_speak(SAYO),)))[4:-1] == [
            '- speak.to ("ささやく"):',
            "    いまできる:",
            '      "サヨ"',
        ]

    def test_people_who_look_alike_are_numbered(self) -> None:
        """見分けのつかない同じ見た目の 2 人は、古い run と同じく「 #1」「 #2」を添えて別々に出る。"""
        assert _table(ActionChoices((_speak(SHADOW_A, SHADOW_B),)))[6:8] == [
            '      "煤けた上着の男 #1"',
            '      "煤けた上着の男 #2"',
        ]

    def test_person_who_cannot_be_whispered_to_is_numbered_with_the_one_who_can(self) -> None:
        """ささやけない見た目の同じ人は「いまできない:」に出るので、ささやける人と番号で呼び分け、理由の中でも同じ番号で呼ぶ。"""
        speak = self._whisper(
            UnavailableAction(
                picked=("ささやく", SHADOW_B),
                argument="to",
                reason=TextWithPeople(template="{who}は眠っている", people={"who": SHADOW_B}),
            )
        )

        assert _table(ActionChoices((speak,)))[3:-1] == [
            '- speak.to ("ささやく"):',
            "    いまできる:",
            '      "煤けた上着の男 #1"',
            "    いまできない:",
            '      "煤けた上着の男 #2"（煤けた上着の男 #2は眠っている）',
        ]

    def test_person_only_in_an_unavailable_reason_is_not_counted(self) -> None:
        """同じ見た目の人がいまはできない理由にだけ出るときは、表に出る 1 人に番号を付けない。"""
        speak = self._whisper(
            UnavailableAction(
                picked=("ささやく", SAYO),
                argument="to",
                reason=TextWithPeople(template="{who}が見ている", people={"who": SHADOW_B}),
            )
        )

        assert _table(ActionChoices((speak,)))[5:-1] == [
            '      "煤けた上着の男"',
            "    いまできない:",
            '      "サヨ"（煤けた上着の男が見ている）',
        ]

    @staticmethod
    def _whisper(unavailable: UnavailableAction) -> ActionChoice:
        content = FreeText(name="content", label="中身")
        return ActionChoice(
            description="説明。",
            name="speak",
            label="話す",
            outline=(
                ArgumentOutline(name="reach", label="届け方", required=True),
                ArgumentOutline(name="to", label="相手"),
                ArgumentOutline(name="content", label="中身"),
            ),
            values=(
                PickOne(
                    name="reach",
                    label="届け方",
                    candidates=(
                        Candidate(
                            label="ささやく",
                            values=(
                                PickOne(
                                    name="to", label="相手", candidates=(Candidate(label=SHADOW_A, values=(content,)),)
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            unavailable=(unavailable,),
        )

    def test_items_with_the_same_name_are_listed_once(self) -> None:
        """同じ名前の品物は、数を添えず 1 回だけ出る。"""
        drop = ActionChoice(
            description="説明。",
            name="drop_item",
            label="置く",
            outline=(ArgumentOutline(name="item", label="品物", required=True),),
            values=(PickOne(name="item", label="品物", candidates=(Candidate(label="ランプの油", count=3),)),),
        )

        assert _table(ActionChoices((drop,))) == ["- drop_item.item:", "    いまできる:", '      "ランプの油"', NOTE]

    def test_value_outside_the_outline_is_named_under_details(self) -> None:
        """見取り図に無い、候補から選ぶ値は「details.名前」の見出しで出る。"""
        lever = Candidate(
            label="レバー",
            values=(PickOne(name="position", label="位置", candidates=(Candidate(label="上"), Candidate(label="下"))),),
        )

        assert _table(ActionChoices((_interact(lever),)))[3] == '- interact.details.position ("レバー"):'

    def test_actions_without_candidates_are_left_out(self) -> None:
        """選ぶ値の無い行動 (待つ) と、候補もいまはできないものも無い行動は、見出しを持たない。"""
        drop = ActionChoice(
            description="説明。",
            name="drop_item",
            label="置く",
            outline=(ArgumentOutline(name="item", label="品物", required=True),),
            values=(PickOne(name="item", label="品物", candidates=()),),
        )

        assert _table(
            ActionChoices((ActionChoice(description="説明。", name="wait", label="待つ"), drop, _travel("井戸")))
        ) == [
            "- travel_to.destination:",
            "    いまできる:",
            '      "井戸"',
            NOTE,
        ]

    def test_no_candidate_at_all_gives_no_table(self) -> None:
        """どの行動にも候補もいまはできないものも無ければ、候補表を出さない。"""
        assert (
            _tools(ActionChoices((ActionChoice(description="説明。", name="wait", label="待つ"),))).candidate_table()
            is None
        )

    def test_whole_action_unavailable_is_listed_with_its_reason(self) -> None:
        """行動ごといまはできない (行為の最中に探す) ものは、「- explore: いまできない（理由）」の 1 行で候補表に出る。
        理由の末尾の句点は落とし、途中の句点は残す。"""
        explore = ActionChoice(
            description="説明。",
            name="explore",
            label="探す",
            unavailable=(UnavailableAction(picked=(), reason="手が離せない。今していることが済むまで待つしかない。"),),
        )

        assert _table(ActionChoices((explore, _travel("井戸")))) == [
            "- explore: いまできない（手が離せない。今していることが済むまで待つしかない）",
            "- travel_to.destination:",
            "    いまできる:",
            '      "井戸"',
            NOTE,
        ]

    def test_each_whole_action_reason_gets_its_own_line(self) -> None:
        """行動ごといまはできない理由が 2 つあれば、渡された順に 1 つ 1 行で出る。"""
        explore = ActionChoice(
            description="説明。",
            name="explore",
            label="探す",
            unavailable=(
                UnavailableAction(picked=(), reason="手が離せない。"),
                UnavailableAction(picked=(), reason="暗くて何も見えない。"),
            ),
        )

        assert _table(ActionChoices((explore,))) == [
            "- explore: いまできない（手が離せない）",
            "- explore: いまできない（暗くて何も見えない）",
            NOTE,
        ]

    def test_action_with_arguments_unavailable_as_a_whole_gives_only_the_one_line(self) -> None:
        """引数のある行動 (travel_to) が行動ごといまはできないなら、引数の見出しは立てず「- travel_to: いまできない（理由）」の 1 行だけが出る。"""
        travel = ActionChoice(
            description="説明。",
            name="travel_to",
            label="移動する",
            outline=(ArgumentOutline(name="destination", label="行き先", required=True),),
            values=(PickOne(name="destination", label="行き先", candidates=()),),
            unavailable=(UnavailableAction(picked=(), reason="手が離せない。"),),
        )

        assert _table(ActionChoices((travel,))) == ["- travel_to: いまできない（手が離せない）", NOTE]

    def test_whole_action_available_gives_no_line(self) -> None:
        """引数の無い行動がいまできるなら、候補表にその行動の行は出ない。"""
        explore = ActionChoice(description="説明。", name="explore", label="探す")

        assert _table(ActionChoices((explore, _travel("井戸")))) == [
            "- travel_to.destination:",
            "    いまできる:",
            '      "井戸"',
            NOTE,
        ]


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


class TestCallText:
    """ActionTools.call_text が、行動を選んだ時点の呼び方で、写せる値だけを引用した呼び出しの文を作ることを保証する。"""

    def test_picked_values_are_quoted_and_the_rest_is_hidden_as_text(self) -> None:
        """候補から選んだ値は引用し、操作の宣言の引数 (details) は「本文」と伏せる。"""
        call = _tools(ActionChoices((_interact(SAFE),))).call_text(
            "interact", {"target": "金庫", "how": "番号を合わせて開ける", "details": {"code": "1907"}}
        )

        assert call == 'interact(target="金庫", how="番号を合わせて開ける", details=本文)'

    def test_whisper_keeps_the_listener_as_the_being_calls_her(self) -> None:
        """サヨにささやくと、相手は呼び方のまま引用し、中身は「本文」と伏せる。"""
        call = _tools(_gen_in_the_office()).call_text("speak", {"reach": "ささやく", "to": "サヨ", "content": "鍵は?"})

        assert call == 'speak(reach="ささやく", to="サヨ", content=本文)'

    def test_being_tools_are_left_out(self) -> None:
        """独白とメモは別の行や欄に出るので、呼び出しの文には出さない。"""
        call = _tools(_gen_in_the_office(), WITH_MEMORY).call_text(
            "travel_to", {"destination": "井戸", "inner_thought": "行こう", "memo": [{"do": "add"}]}
        )

        assert call == 'travel_to(destination="井戸")'

    def test_quoted_values_come_first_in_the_outline_order_whatever_the_llm_wrote(self) -> None:
        """LLM が書いた順によらず、引用する値を見取り図の順に先に並べ、伏せる文をそのあとに見取り図の順で並べる。"""
        call = _tools(ActionChoices((_interact(SAFE),))).call_text(
            "interact",
            {"say_inline": "開けるぞ", "details": {"code": "1907"}, "how": "番号を合わせて開ける", "target": "金庫"},
        )

        assert call == 'interact(target="金庫", how="番号を合わせて開ける", say_inline=本文, details=本文)'

    def test_value_is_hidden_with_the_word_the_outline_gives(self) -> None:
        """見取り図が伏せる言葉 (発言) を持つ引数は、その言葉で伏せ、持たない引数は「本文」で伏せる。"""
        wait = ActionChoice(
            description="説明。",
            name="wait",
            label="待つ",
            outline=(
                ArgumentOutline(name="say_inline", label="一言", hidden_as="発言"),
                ArgumentOutline(name="note", label="覚え"),
            ),
        )

        call = _tools(ActionChoices((wait,))).call_text("wait", {"note": "あとで", "say_inline": "待つぞ"})

        assert call == "wait(say_inline=発言, note=本文)"

    def test_arguments_outside_the_outline_follow_in_name_order(self) -> None:
        """見取り図に無い引数は、見取り図の引数のあとに、名前の順で並ぶ。"""
        call = _tools(_gen_in_the_office()).call_text("travel_to", {"zeta": "1", "destination": "井戸", "alpha": "2"})

        assert call == 'travel_to(destination="井戸", alpha=本文, zeta=本文)'

    def test_tool_that_was_not_offered_has_no_call_text(self) -> None:
        """出していないツールの名前なら None を返す。"""
        assert _tools(_gen_in_the_office()).call_text("gather", {}) is None


class _Rechoose:
    """呼ばれた問いを覚え、決めた答えを返す選び直し。"""

    def __init__(self, answers: dict[str, str | None] | None = None) -> None:
        self.asked: list[tuple[str, str, dict[str, str | None], str | None]] = []
        self._answers = answers or {}

    def __call__(
        self, written: str, label: str, candidates: Mapping[str, str | None], parent: str | None
    ) -> str | None:
        self.asked.append((written, label, dict(candidates), parent))
        return self._answers.get(written)


def _safe_that_cannot_be_opened() -> ActionChoice:
    """金庫は番号を合わせて開けられるが、ただ「開ける」ことはできず、物置は操作がどれもできない。"""
    interact = _interact(SAFE)
    return ActionChoice(
        description="説明。",
        name=interact.name,
        label=interact.label,
        outline=interact.outline,
        takes_details=True,
        values=interact.values,
        unavailable=(
            UnavailableAction(picked=("金庫", "開ける"), argument="how", reason="鍵が掛かっている"),
            UnavailableAction(picked=("物置", "開ける"), argument="how", reason="錠前が錆びている"),
        ),
    )


class TestNamesMatched:
    """ActionTools.with_names_matched が、候補から選ぶ値を候補の名前に合わせ、当たらない名前だけを選び直しに回すことを保証する。"""

    def test_name_in_the_candidates_is_not_asked(self) -> None:
        """候補に当たる名前 (金庫・番号を合わせて開ける) は、選び直しに回さず、そのまま返す。"""
        rechoose = _Rechoose()
        arguments = {"target": "金庫", "how": "番号を合わせて開ける", "details": {"code": "1907"}}

        matched = _tools(ActionChoices((_interact(SAFE),))).with_names_matched("interact", arguments, rechoose)

        assert matched == arguments and rechoose.asked == []

    def test_copied_display_form_is_fixed_without_asking(self) -> None:
        """引用符つきの名前 ("金庫") は、選び直しに回さず、候補の名前に直す。"""
        rechoose = _Rechoose()

        matched = _tools(ActionChoices((_interact(SAFE),))).with_names_matched(
            "interact", {"target": '"金庫"', "how": "番号を合わせて開ける"}, rechoose
        )

        assert matched == {"target": "金庫", "how": "番号を合わせて開ける"} and rechoose.asked == []

    def test_unmatched_target_is_rechosen_and_the_operation_under_it_is_matched(self) -> None:
        """当たらない対象 (safe) は、対象の候補と、候補の下の操作を説明に添えて選び直しに回し、選び直した対象の下で操作を照合する。"""
        rechoose = _Rechoose({"safe": "金庫"})

        matched = _tools(ActionChoices((_interact(SAFE),))).with_names_matched(
            "interact", {"target": "safe", "how": "番号を合わせて開ける"}, rechoose
        )

        assert matched == {"target": "金庫", "how": "番号を合わせて開ける"}
        assert rechoose.asked == [("safe", "相手", {"金庫": "番号を合わせて開ける"}, None)]

    def test_unmatched_operation_is_asked_under_its_target(self) -> None:
        """当たらない操作 (open) は、どの候補の下の操作かを添えて選び直しに回す。"""
        rechoose = _Rechoose({"open": "番号を合わせて開ける"})

        matched = _tools(ActionChoices((_interact(SAFE),))).with_names_matched(
            "interact", {"target": "金庫", "how": "open"}, rechoose
        )

        assert matched == {"target": "金庫", "how": "番号を合わせて開ける"}
        assert rechoose.asked == [("open", "操作", {"番号を合わせて開ける": None}, "金庫")]

    def test_unavailable_operation_is_passed_on_without_asking(self) -> None:
        """いまできない金庫の「開ける」を引用符つきで書くと、選び直しに回さず「開ける」に直して世界に渡す。世界が理由を付けて断る。

        選び直しに回すと、当たる候補がいまできるものしか無いので、別の操作に寄せられるおそれがある。
        """
        rechoose = _Rechoose({"開ける": "番号を合わせて開ける"})

        matched = _tools(ActionChoices((_safe_that_cannot_be_opened(),))).with_names_matched(
            "interact", {"target": "金庫", "how": '"開ける"'}, rechoose
        )

        assert matched == {"target": "金庫", "how": "開ける"} and rechoose.asked == []

    def test_target_whose_every_operation_is_unavailable_is_passed_on_without_asking(self) -> None:
        """操作がどれもいまできず候補に並ばない物置とその「開ける」を引用符つきで書いても、選び直しに回さず、表記だけ直して世界に渡す。"""
        rechoose = _Rechoose({"物置": "金庫"})

        matched = _tools(ActionChoices((_safe_that_cannot_be_opened(),))).with_names_matched(
            "interact", {"target": '"物置"', "how": '"開ける"'}, rechoose
        )

        assert matched == {"target": "物置", "how": "開ける"} and rechoose.asked == []

    def test_unavailable_name_under_another_candidate_is_still_asked(self) -> None:
        """金庫の下でいまできない「開ける」でも、別の対象 (レバー) の下に書けば、いまできない名前としては扱わず選び直しに回す。"""
        lever = Candidate(
            label="レバー", values=(PickOne(name="how", label="操作", candidates=(Candidate(label="引く"),)),)
        )
        interact = _safe_that_cannot_be_opened()
        choice = ActionChoice(
            description="説明。",
            name=interact.name,
            label=interact.label,
            outline=interact.outline,
            takes_details=True,
            values=(PickOne(name="target", label="相手", candidates=(SAFE, lever)),),
            unavailable=interact.unavailable,
        )
        rechoose = _Rechoose()

        _tools(ActionChoices((choice,))).with_names_matched("interact", {"target": "レバー", "how": "開ける"}, rechoose)

        assert [asked[0] for asked in rechoose.asked] == ["開ける"]

    def test_name_not_rechosen_is_left_as_written(self) -> None:
        """選び直しが名前を返さなければ、書かれた名前のまま返す。世界が場面に合わないと断る。"""
        matched = _tools(_gen_in_the_office()).with_names_matched("travel_to", {"destination": "天守閣"}, _Rechoose())

        assert matched == {"destination": "天守閣"}

    def test_value_without_candidates_is_not_asked(self) -> None:
        """候補が空の値は、選び直しに回さない。伏せた候補の有無を、問いで漏らさないため。"""
        rechoose = _Rechoose()
        drop = ActionChoice(
            description="説明。",
            name="drop_item",
            label="置く",
            outline=(ArgumentOutline(name="item", label="品物", required=True),),
            values=(PickOne(name="item", label="品物", candidates=()),),
        )

        _tools(ActionChoices((drop,))).with_names_matched("drop_item", {"item": "ランプ"}, rechoose)

        assert rechoose.asked == []

    @pytest.mark.parametrize("written", ["", "  "])
    def test_blank_name_is_not_asked(self, written: str) -> None:
        """空や空白だけの名前は、選び直しに回さず、書かれたまま返す。世界が場面に合わないと断る。"""
        rechoose = _Rechoose()

        matched = _tools(ActionChoices((_interact(SAFE),))).with_names_matched(
            "interact", {"target": written}, rechoose
        )

        assert matched == {"target": written} and rechoose.asked == []

    def test_operation_in_details_is_matched_there(self) -> None:
        """見取り図に無い操作を details に書いたとき、details の中の名前を選び直して、details の中で置き換える。"""
        rechoose = _Rechoose({"open": "番号を合わせて開ける"})

        matched = _tools(ActionChoices((_interact_without_how(),))).with_names_matched(
            "interact", {"target": "金庫", "details": {"how": "open"}}, rechoose
        )

        assert matched == {"target": "金庫", "details": {"how": "番号を合わせて開ける"}}

    def test_operation_written_on_top_wins_over_details(self) -> None:
        """見取り図に無い操作を上の段と details の両方に書いたとき、行為に使われる上の段の名前を選び直す。"""
        rechoose = _Rechoose({"open": "番号を合わせて開ける"})

        matched = _tools(ActionChoices((_interact_without_how(),))).with_names_matched(
            "interact", {"target": "金庫", "how": "open", "details": {"how": "番号を合わせて開ける"}}, rechoose
        )

        assert matched["how"] == "番号を合わせて開ける"
        assert [asked[0] for asked in rechoose.asked] == ["open"]

    def test_details_of_an_action_without_details_are_not_asked(self) -> None:
        """details を取らない行動では、details に書いた操作は行為に渡らないので、選び直しに回さない。"""
        rechoose = _Rechoose({"open": "番号を合わせて開ける"})
        interact = ActionChoice(
            description="説明。",
            name="interact",
            label="操作する",
            outline=(
                ArgumentOutline(name="target", label="相手", required=True),
                ArgumentOutline(name="how", label="操作"),
            ),
            values=(PickOne(name="target", label="相手", candidates=(LOCKED_SAFE,)),),
        )

        _tools(ActionChoices((interact,))).with_names_matched(
            "interact", {"target": "金庫", "details": {"how": "open"}}, rechoose
        )

        assert rechoose.asked == []


LOCKED_SAFE = Candidate(
    label="金庫",
    values=(PickOne(name="how", label="操作", candidates=(Candidate(label="番号を合わせて開ける"),)),),
)


def _interact_without_how() -> ActionChoice:
    return ActionChoice(
        description="説明。",
        name="interact",
        label="操作する",
        outline=(ArgumentOutline(name="target", label="相手", required=True),),
        takes_details=True,
        values=(PickOne(name="target", label="相手", candidates=(SAFE,)),),
    )
