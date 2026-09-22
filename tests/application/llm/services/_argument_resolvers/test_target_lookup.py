"""TargetIndex が、書かれた名前 1 つにつき参照 1 回で「当たり / 曖昧 / 種類違い / 無い」を返す。"""

from __future__ import annotations

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
from ai_rpg_world.application.llm.services._argument_resolvers.target_lookup import (
    Ambiguous,
    Found,
    NotFound,
    TargetIndex,
    WrongKind,
    label_forms,
)


def _t(label: str, kind: str, name: str) -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(label=label, kind=kind, display_name=name)


def _index() -> TargetIndex:
    return TargetIndex({
        "O1": _t("O1", "spot_graph_object", "貝の岩棚"),
        "O2": _t("O2", "spot_graph_object", "リン"),
        "P1": _t("P1", "spot_graph_player", "リン"),
        "M1": _t("M1", "spot_graph_monster", "大型カニ"),
    })


class TestLookupOutcomes:
    def test_a_unique_name_of_an_accepted_kind_is_found(self) -> None:
        """受け付ける種別に 1 件だけ当たる名前は Found になる。"""
        out = _index().lookup("貝の岩棚", accept_kinds=("spot_graph_object",))

        assert isinstance(out, Found)
        assert out.target.label == "O1"

    def test_a_name_shared_across_accepted_kinds_is_ambiguous(self) -> None:
        """受け付ける複数の種別に同名があると Ambiguous になり、両方が並ぶ。"""
        out = _index().lookup("リン", accept_kinds=("spot_graph_object", "spot_graph_player"))

        assert isinstance(out, Ambiguous)
        assert {t.label for t in out.targets} == {"O2", "P1"}

    def test_a_name_of_another_kind_is_wrong_kind_with_the_accepted_candidates(self) -> None:
        """別の種別にだけ在る名前は WrongKind になり、受け付ける種別の候補も持つ。"""
        out = _index().lookup("大型カニ", accept_kinds=("spot_graph_object",))

        assert isinstance(out, WrongKind)
        assert out.target.kind == "spot_graph_monster"
        assert [t.label for t in out.candidates] == ["O1", "O2"]

    def test_a_name_nowhere_is_not_found_with_the_accepted_candidates(self) -> None:
        """どこにも無い名前は NotFound になり、受け付ける種別の候補を持つ。"""
        out = _index().lookup("大樫の樹", accept_kinds=("spot_graph_object",))

        assert isinstance(out, NotFound)
        assert [t.label for t in out.candidates] == ["O1", "O2"]

    def test_a_quoted_prompt_line_resolves_by_its_name(self) -> None:
        """引用符つき・行の丸写しでも、分解した形で当たる。"""
        out = _index().lookup('"貝の岩棚"', accept_kinds=("spot_graph_object",))

        assert isinstance(out, Found)


class TestInternalLabelsAreOnlyAWayOutOfAmbiguity:
    def test_an_internal_label_still_resolves_when_no_name_matches(self) -> None:
        """表示名で当たらないとき、内部ラベル (P1) でも引ける。同名衝突の唯一の出口。"""
        out = _index().lookup("P1", accept_kinds=("spot_graph_player",))

        assert isinstance(out, Found)
        assert out.target.display_name == "リン"

    def test_a_display_name_wins_over_an_internal_label_of_the_same_text(self) -> None:
        """表示名と内部ラベルが同じ文字列なら表示名を採る。当人が見ているのは名前の方。"""
        index = TargetIndex({
            "P1": _t("P1", "spot_graph_player", "O1"),
            "O1": _t("O1", "spot_graph_object", "岩"),
        })

        out = index.lookup("O1", accept_kinds=("spot_graph_player", "spot_graph_object"))

        assert isinstance(out, Found)
        assert out.target.label == "P1"


class TestLabelForms:
    def test_forms_keep_order_and_drop_duplicates(self) -> None:
        """丸写し行から、そのまま・ラベル・名前の順で形が出て、同じ形は 1 度だけ。"""
        assert label_forms("S2: 禁書扉 → 館長書斎") == ["S2: 禁書扉 → 館長書斎", "S2", "館長書斎", "禁書扉 → 館長書斎", "禁書扉"]

    def test_blank_has_no_forms(self) -> None:
        assert label_forms("   ") == []
