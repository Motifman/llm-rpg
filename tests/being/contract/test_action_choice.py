"""環境が毎ターン Being に渡す行動の選択肢 (ActionChoice) の決まりを保証する (design_decisions D2226)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import (
    ActionChoice,
    ActionChoices,
    ArgumentOutline,
    Candidate,
    ContractViolation,
    FreeText,
    PersonInText,
    PickOne,
    TextWithPeople,
    UnavailableAction,
    UnidentifiedPerson,
)

_SAYO = PersonInText(handle=2, appearance="三つ編みの娘", visible_name="サヨ")
_CODE = FreeText(name="code", label="番号")
_TRAVEL_OUTLINE = (ArgumentOutline(name="destination", label="行き先", required=True),)
_INTERACT_OUTLINE = (
    ArgumentOutline(name="target", label="相手", required=True),
    ArgumentOutline(name="how", label="操作"),
)


def _travel(*candidates: str) -> ActionChoice:
    return ActionChoice(
        description="説明。",
        name="travel_to",
        label="行く",
        outline=_TRAVEL_OUTLINE,
        values=(PickOne(name="destination", label="行き先", candidates=tuple(Candidate(label=c) for c in candidates)),),
    )


class TestActionChoice:
    """行動の種類ごとに 1 つの選択肢が、相手の候補と、自由に書く文字と、いまはできない理由を持つことを保証する。"""

    def test_gen_in_the_office_can_open_the_safe_with_a_code(self) -> None:
        """「操作する」は、相手の候補 (金庫・サヨ) の下に操作の候補を持ち、金庫の「番号を合わせて開ける」は番号を自由に書く文字で受ける。"""
        open_safe = Candidate(label="番号を合わせて開ける", values=(_CODE,))
        choice = ActionChoice(
            description="説明。",
            name="interact",
            label="操作する",
            outline=_INTERACT_OUTLINE,
            takes_details=True,
            values=(
                PickOne(
                    name="target",
                    label="相手",
                    candidates=(
                        Candidate(label="金庫", values=(PickOne(name="how", label="操作", candidates=(open_safe,)),)),
                        Candidate(
                            label=_SAYO,
                            values=(PickOne(name="how", label="操作", candidates=(Candidate(label="肩を叩く"),)),),
                        ),
                    ),
                ),
            ),
        )

        [target] = choice.values
        assert isinstance(target, PickOne)
        safe, _ = target.candidates
        [how] = safe.values
        assert isinstance(how, PickOne)
        assert [c.label for c in target.candidates] == ["金庫", _SAYO]
        assert how.candidates[0].values == (_CODE,)
        assert choice.can_be_chosen()

    def test_holding_the_lamp_is_unavailable_with_a_reason(self) -> None:
        """「持つ」のランプがいまはできないなら、候補に入れず、選んだ道筋と理由を unavailable に持つ。ほかに候補が無ければ選べない。"""
        choice = ActionChoice(
            description="説明。",
            name="hold_item",
            label="手に持つ",
            outline=(ArgumentOutline(name="item", label="品物", required=True),),
            values=(PickOne(name="item", label="品物", candidates=()),),
            unavailable=(UnavailableAction(picked=("ランプ",), argument="item", reason="両手がふさがっている"),),
        )

        assert choice.unavailable[0].picked == ("ランプ",)
        assert not choice.can_be_chosen()

    def test_unavailable_path_names_the_argument_of_its_last_step(self) -> None:
        """道筋のある「いまはできない」は、最後の名前がどの引数の候補かを argument に持つ。無ければ表のどの行に置くか決まらないので拒む。"""
        with pytest.raises(ContractViolation, match="argument"):
            UnavailableAction(picked=("ランプ",), reason="両手がふさがっている")

    def test_whole_action_unavailable_has_no_argument(self) -> None:
        """道筋の無い「いまはできない」(行動ごとできない) に argument を付けると拒む。"""
        with pytest.raises(ContractViolation, match="argument"):
            UnavailableAction(picked=(), argument="item", reason="手が離せない")

    def test_argument_outside_the_outline_is_rejected_unless_the_action_takes_details(self) -> None:
        """見取り図に無い引数の名前は、details を取らない行動では拒む。details を取る行動では details の下の値として受け入れる。"""
        oil = UnavailableAction(picked=("ランプ", "油を差す"), argument="how", reason="油が無い")
        item = (ArgumentOutline(name="item", label="品物", required=True),)
        values = (PickOne(name="item", label="品物", candidates=()),)

        with pytest.raises(ContractViolation, match="argument"):
            ActionChoice(
                description="説明。",
                name="hold_item",
                label="手に持つ",
                outline=item,
                values=values,
                unavailable=(oil,),
            )
        ActionChoice(
            description="説明。",
            name="use",
            label="使う",
            outline=item,
            takes_details=True,
            values=values,
            unavailable=(oil,),
        )

    def test_action_without_values_is_chosen_as_it_is(self) -> None:
        """値の無い行動 (耳を澄ます) は、いまはできない理由が無ければ選べる。"""
        assert ActionChoice(description="説明。", name="listen", label="耳を澄ます").can_be_chosen()

    def test_whole_action_unavailable_cannot_be_chosen(self) -> None:
        """選んだ道筋の無い理由 (行っているあいだ) を持つ行動は、選べない。"""
        choice = ActionChoice(
            description="説明。",
            name="listen",
            label="耳を澄ます",
            unavailable=(UnavailableAction(picked=(), reason="手が離せない"),),
        )

        assert not choice.can_be_chosen()

    def test_reason_may_name_people_and_a_blank_reason_is_rejected(self) -> None:
        """理由には、人のプレースホルダーを持つ文を使える。空白だけの文字の理由は拒む。"""
        reason = TextWithPeople(template="{target}は眠っている", people={"target": _SAYO})

        UnavailableAction(picked=(_SAYO,), argument="target", reason=reason)
        with pytest.raises(ContractViolation, match="reason"):
            UnavailableAction(picked=(_SAYO,), argument="target", reason="  ")

    def test_same_reason_naming_people_twice_is_rejected_as_a_contract_violation(self) -> None:
        """人のプレースホルダーを持つ同じ理由の「いまはできない」が 2 回並ぶと、型の誤りではなく ContractViolation で拒む。"""
        reason = TextWithPeople(template="{target}は眠っている", people={"target": _SAYO})
        asleep = UnavailableAction(picked=(_SAYO,), argument="target", reason=reason)

        with pytest.raises(ContractViolation, match="unavailable"):
            ActionChoice(
                description="説明。",
                name="tend_to_player",
                label="介抱する",
                outline=(ArgumentOutline(name="target", label="相手", required=True),),
                values=(PickOne(name="target", label="相手", candidates=()),),
                unavailable=(asleep, asleep),
            )

    def test_unavailable_path_that_is_also_a_candidate_is_rejected(self) -> None:
        """いまはできない道筋が、候補としても並んでいると拒む。"""
        with pytest.raises(ContractViolation, match="unavailable"):
            ActionChoice(
                description="説明。",
                name="travel_to",
                label="行く",
                outline=_TRAVEL_OUTLINE,
                values=_travel("井戸").values,
                unavailable=(UnavailableAction(picked=("井戸",), argument="destination", reason="道が埋まっている"),),
            )

    def test_same_unavailable_action_twice_is_rejected(self) -> None:
        """同じ道筋と理由の「いまはできない」が 2 回並ぶと拒む。"""
        blocked = UnavailableAction(picked=("北の坑道",), argument="destination", reason="道が通じていない")

        with pytest.raises(ContractViolation, match="unavailable"):
            ActionChoice(
                description="説明。",
                name="travel_to",
                label="行く",
                outline=_TRAVEL_OUTLINE,
                values=_travel().values,
                unavailable=(blocked, blocked),
            )

    def test_value_name_repeated_along_a_path_is_rejected_but_siblings_may_share_it(self) -> None:
        """候補の下の値が、外側の値と同じ名前だと拒む。別々の候補の下で同じ名前 (how) を使うのはよい。"""
        how = PickOne(name="how", label="操作", candidates=(Candidate(label="叩く"),))
        siblings = PickOne(
            name="target",
            label="相手",
            candidates=(Candidate(label="扉", values=(how,)), Candidate(label="箱", values=(how,))),
        )
        repeated = PickOne(
            name="target",
            label="相手",
            candidates=(Candidate(label="扉", values=(FreeText(name="target", label="宛先"),)),),
        )

        ActionChoice(
            description="説明。",
            name="interact",
            label="操作する",
            outline=_INTERACT_OUTLINE,
            takes_details=True,
            values=(siblings,),
        )
        with pytest.raises(ContractViolation, match="path"):
            ActionChoice(
                description="説明。",
                name="interact",
                label="操作する",
                outline=_INTERACT_OUTLINE,
                takes_details=True,
                values=(repeated,),
            )

    def test_nested_pick_without_candidates_is_rejected(self) -> None:
        """候補の下の「候補から選ぶ値」が空だと、選んでも行き止まりになるので拒む。いちばん上の空は、選べない選択肢として通す。"""
        dead_end = PickOne(
            name="target",
            label="相手",
            candidates=(Candidate(label="金庫", values=(PickOne(name="how", label="操作", candidates=()),)),),
        )

        with pytest.raises(ContractViolation, match="nested"):
            ActionChoice(
                description="説明。",
                name="interact",
                label="操作する",
                outline=_INTERACT_OUTLINE,
                takes_details=True,
                values=(dead_end,),
            )

    def test_whole_action_unavailable_with_candidates_is_rejected(self) -> None:
        """行動ごと選べない理由を持ちながら、候補を持つ選択肢は拒む。"""
        with pytest.raises(ContractViolation, match="unavailable"):
            ActionChoice(
                description="説明。",
                name="travel_to",
                label="行く",
                outline=_TRAVEL_OUTLINE,
                values=_travel("井戸").values,
                unavailable=(UnavailableAction(picked=(), reason="手が離せない"),),
            )

    @pytest.mark.parametrize("name", ["行く", "travel to", "", "1st", "a" * 65])
    def test_name_must_be_a_short_ascii_identifier(self, name: str) -> None:
        """選択肢と値の名前は、LLM のツールと引数の名前になるので、64 文字までの ASCII の識別子でないと拒む。"""
        with pytest.raises(ContractViolation, match="name"):
            ActionChoice(description="説明。", name=name, label="行く")
        with pytest.raises(ContractViolation, match="name"):
            FreeText(name=name, label="番号")
        with pytest.raises(ContractViolation, match="name"):
            PickOne(name=name, label="行き先", candidates=())

    def test_same_text_candidate_twice_is_rejected(self) -> None:
        """1 つの候補の並びに、同じ文字の候補が 2 つあると拒む。同じ名前の品物は数を添えた 1 つの候補にする。"""
        with pytest.raises(ContractViolation, match="candidates"):
            _travel("井戸", "井戸")

    def test_same_person_twice_is_rejected_but_people_with_the_same_look_are_kept(self) -> None:
        """同じ印 (handle) の人が 2 回並ぶと拒む。見た目が同じでも印が違えば別の候補で、呼び分けは Being が付ける。"""
        twin = PersonInText(handle=3, appearance=_SAYO.appearance, visible_name=None)
        stranger = PersonInText(handle=4, appearance=_SAYO.appearance, visible_name=None)

        PickOne(name="target", label="相手", candidates=(Candidate(label=twin), Candidate(label=stranger)))
        with pytest.raises(ContractViolation, match="candidates"):
            PickOne(name="target", label="相手", candidates=(Candidate(label=_SAYO), Candidate(label=_SAYO)))

    def test_items_with_the_same_name_are_one_candidate_with_a_count(self) -> None:
        """同じ名前の品物は、数 (count) を添えた 1 つの候補になる。数は 1 以上。"""
        assert Candidate(label="ランプの油", count=3).count == 3
        with pytest.raises(ContractViolation, match="count"):
            Candidate(label="ランプの油", count=0)

    def test_same_value_name_twice_is_rejected(self) -> None:
        """1 つの値の並びに、同じ名前の値が 2 つあると拒む。"""
        with pytest.raises(ContractViolation, match="values"):
            Candidate(label="金庫", values=(_CODE, FreeText(name="code", label="合言葉")))


class TestArgumentOutline:
    """行動の種類ごとに変わらない引数の見取り図 (outline・takes_details) と、値の名前との決まりを保証する。"""

    @pytest.mark.parametrize("max_length", [0, -1, True, 1.5])
    def test_max_length_must_be_a_positive_int(self, max_length: object) -> None:
        """長さの上限が正の整数でなければ拒む。上限を付けないなら None にする。"""
        with pytest.raises(ContractViolation, match="max_length"):
            ArgumentOutline(name="say_inline", label="一言", max_length=max_length)  # type: ignore[arg-type]

    @pytest.mark.parametrize("hidden_as", ["", "  "])
    def test_blank_hidden_as_is_rejected(self, hidden_as: str) -> None:
        """伏せるときの言葉が空か空白だけなら拒む。伏せないなら None にする。"""
        with pytest.raises(ContractViolation, match="hidden_as"):
            ArgumentOutline(name="say_inline", label="一言", hidden_as=hidden_as)

    def test_top_level_value_missing_from_outline_is_rejected(self) -> None:
        """いちばん上の値の名前が見取り図に無いと拒む。上の段の引数は、候補の無いターンにも同じ顔ぶれで並べるため。"""
        with pytest.raises(ContractViolation, match="outline"):
            ActionChoice(
                description="説明。",
                name="travel_to",
                label="行く",
                values=(PickOne(name="destination", label="行き先", candidates=()),),
            )

    def test_nested_value_outside_outline_needs_takes_details(self) -> None:
        """候補の下の、見取り図に無い値 (金庫の番号) は、takes_details が偽だと拒み、真なら通す。"""
        safe = PickOne(
            name="target",
            label="相手",
            candidates=(
                Candidate(
                    label="金庫",
                    values=(
                        PickOne(
                            name="how",
                            label="操作",
                            candidates=(Candidate(label="番号を合わせて開ける", values=(_CODE,)),),
                        ),
                    ),
                ),
            ),
        )

        ActionChoice(
            description="説明。",
            name="interact",
            label="操作する",
            outline=_INTERACT_OUTLINE,
            takes_details=True,
            values=(safe,),
        )
        with pytest.raises(ContractViolation, match="outline"):
            ActionChoice(
                description="説明。", name="interact", label="操作する", outline=_INTERACT_OUTLINE, values=(safe,)
            )

    def test_required_outline_without_its_top_level_value_is_rejected(self) -> None:
        """必須の見取り図 (行き先) に当たるいちばん上の値が無いと拒む。値の無いターンにツールの必須の引数が消えないため。"""
        with pytest.raises(ContractViolation, match="required"):
            ActionChoice(description="説明。", name="travel_to", label="行く", outline=_TRAVEL_OUTLINE)

    def test_top_level_value_for_an_optional_outline_is_rejected(self) -> None:
        """必須でない見取り図 (how) の名前で、いちばん上に値を置くと拒む。いちばん上の値は毎ターン必ず渡る引数だけにする。"""
        how = PickOne(name="how", label="操作", candidates=())

        with pytest.raises(ContractViolation, match="required"):
            ActionChoice(
                description="説明。",
                name="interact",
                label="操作する",
                outline=_INTERACT_OUTLINE,
                values=(PickOne(name="target", label="相手", candidates=()), how),
            )

    def test_outline_repeating_a_name_is_rejected(self) -> None:
        """見取り図に同じ名前が 2 つあると拒む。名前はツールの引数の名前になる。"""
        target = ArgumentOutline(name="target", label="相手")

        with pytest.raises(ContractViolation, match="outline"):
            ActionChoice(description="説明。", name="interact", label="操作する", outline=(target, target))

    def test_outline_name_must_be_a_short_ascii_identifier(self) -> None:
        """見取り図の名前は、64 文字までの ASCII の識別子でないと拒む。"""
        with pytest.raises(ContractViolation, match="name"):
            ArgumentOutline(name="相手", label="相手")


class TestActionChoices:
    """1 ターン分の行動の選択肢の並びの決まりを保証する。"""

    def test_choices_are_kept_in_order(self) -> None:
        """渡した順のまま読める。"""
        listen = ActionChoice(description="説明。", name="listen", label="耳を澄ます")

        assert ActionChoices((_travel("井戸"), listen)).choices == (_travel("井戸"), listen)

    def test_people_in_candidates_paths_and_reasons_are_collected(self) -> None:
        """候補、いまはできない道筋、理由の文に出る人を、すべて拾う。見分けられない人は拾わない。"""
        stranger = PersonInText(handle=7, appearance="煤けた上着の男", visible_name=None)
        watcher = PersonInText(handle=9, appearance="背の高い男", visible_name=None)
        reason = TextWithPeople(
            template="{who}と{other}が見ている", people={"who": watcher, "other": UnidentifiedPerson()}
        )
        tend = ActionChoice(
            description="説明。",
            name="tend_to_player",
            label="介抱する",
            outline=(ArgumentOutline(name="target", label="相手", required=True),),
            values=(PickOne(name="target", label="相手", candidates=(Candidate(label=_SAYO),)),),
            unavailable=(UnavailableAction(picked=(stranger,), argument="target", reason=reason),),
        )

        assert set(ActionChoices((tend,)).people()) == {_SAYO, stranger, watcher}

    def test_same_choice_name_twice_is_rejected(self) -> None:
        """同じ名前の選択肢が 2 つあると拒む。名前は LLM のツールの名前になる。"""
        with pytest.raises(ContractViolation, match="choices"):
            ActionChoices((_travel("井戸"), _travel("鍛冶場")))


class TestListingWhatTheSceneDoesNotShow:
    """場面のほかの所に出ていない候補を Being が並べるための印 (listed・fixed_values・writes・asks・shown_under・note) の決まりを保証する。"""

    def test_fixed_values_are_kept_in_order_and_must_not_repeat(self) -> None:
        """固定の値 (話し方) は渡した順で持ち、同じ値が 2 つあると拒む。"""
        assert ArgumentOutline(name="reach", label="届け方", fixed_values=["叫ぶ", "ささやく"]).fixed_values == (
            "叫ぶ",
            "ささやく",
        )
        with pytest.raises(ContractViolation, match="fixed_values"):
            ArgumentOutline(name="reach", label="届け方", fixed_values=("叫ぶ", "叫ぶ"))

    def test_listed_argument_with_fixed_values_is_rejected(self) -> None:
        """固定の値はツールの定義に書くので、並べる印と一緒に付けると拒む。"""
        with pytest.raises(ContractViolation, match="fixed values"):
            ArgumentOutline(name="reach", label="届け方", listed=True, fixed_values=("叫ぶ",))

    def test_asks_must_say_what_to_write(self) -> None:
        """いまできない道筋の asks に、何を書くかを持たない値を入れると拒む。行動ごとできないものに asks を付けても拒む。"""
        with pytest.raises(ContractViolation, match="asks"):
            UnavailableAction(picked=("金庫", "開ける"), argument="how", reason="鍵", asks=(_CODE,))
        with pytest.raises(ContractViolation, match="ask"):
            UnavailableAction(
                picked=(), reason="手が離せない", asks=(FreeText(name="code", label="番号", writes="番号"),)
            )

    def test_shown_under_is_only_for_a_first_step(self) -> None:
        """頭に置く名前 (shown_under) は、2 段の道筋のいまできないものや、候補の下の候補には付けられない。"""
        with pytest.raises(ContractViolation, match="one-step"):
            UnavailableAction(picked=("籠", "乗る"), argument="how", reason="満員", shown_under="昇降機の籠")
        nested = PickOne(
            name="target",
            label="相手",
            candidates=(
                Candidate(
                    label="籠",
                    values=(
                        PickOne(name="how", label="操作", candidates=(Candidate(label="乗る", shown_under="昇降機"),)),
                    ),
                ),
            ),
        )
        with pytest.raises(ContractViolation, match="first step"):
            ActionChoice(
                description="説明。",
                name="interact",
                label="操作する",
                outline=_INTERACT_OUTLINE,
                takes_details=True,
                values=(nested,),
            )

    def test_blank_note_is_rejected(self) -> None:
        """並べない引数の書き方を伝える注記が空白だけなら拒む。注記を付けないなら None にする。"""
        assert ActionChoices((), note=None).note is None
        with pytest.raises(ContractViolation, match="note"):
            ActionChoices((), note=" ")
