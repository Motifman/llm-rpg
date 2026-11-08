from __future__ import annotations

from ai_rpg_world.game_world.domain.design_flaw import (
    DesignFlaw,
    DesignLocation,
    DesignWarning,
    NoScenarioFile,
    ScenarioFile,
)


class TestDesignLocation:
    """DesignLocation が、シナリオの形式に頼らない言い方で宣言の中の場所を表すことを保証する。"""

    def test_keeps_declaration_kind_name_and_field(self) -> None:
        """DesignLocation("object", "lift_lever", "state_keys[0]") は、宣言の種類・名前・欄をそのまま持つ。"""
        location = DesignLocation("object", "lift_lever", "state_keys[0]")

        assert (location.declaration, location.name, location.field) == ("object", "lift_lever", "state_keys[0]")

    def test_same_parts_mean_the_same_location(self) -> None:
        """種類・名前・欄が同じ DesignLocation は等しい。"""
        assert DesignLocation("object", "lift_lever", "spot_id") == DesignLocation("object", "lift_lever", "spot_id")

    def test_reads_as_declaration_kind_quoted_name_and_field(self) -> None:
        """DesignLocation("object", "lift_lever", "state_keys[0]") を文にすると「object 'lift_lever' state_keys[0]」になる。"""
        assert str(DesignLocation("object", "lift_lever", "state_keys[0]")) == "object 'lift_lever' state_keys[0]"

    def test_location_without_file_is_not_from_any_scenario_file(self) -> None:
        """ファイルを渡さずに作った場所 (ドメインが照らし合わせて見つけた誤り) は、NoScenarioFile を持つ。"""
        assert DesignLocation("object", "lift_lever", "spot_id").file == NoScenarioFile()

    def test_location_in_file_reads_with_the_file_first(self) -> None:
        """共通の部品 common/ja_default.yaml の中の場所を文にすると、ファイルの名前が先頭に付く。"""
        location = DesignLocation("world", "world", "rules.fatigue.limit").in_file(
            ScenarioFile("common/ja_default.yaml")
        )

        assert str(location) == "common/ja_default.yaml: world 'world' rules.fatigue.limit"

    def test_same_place_in_different_files_are_different_locations(self) -> None:
        """種類・名前・欄が同じでも、シナリオと共通の部品のように、ファイルが違えば等しくない。"""
        location = DesignLocation("spot", "mine", "name")

        assert location.in_file(ScenarioFile("mine.yaml")) != location.in_file(ScenarioFile("common.yaml"))


class TestDesignFlawAndWarning:
    """読み込みを止める誤り (DesignFlaw) と、読み込みを続ける注意 (DesignWarning) が、場所と理由を持ち、互いに取り違えられないことを保証する。"""

    def test_flaw_keeps_location_and_reason(self) -> None:
        """DesignFlaw は渡した場所と理由をそのまま持つ。"""
        location = DesignLocation("character", "aki", "spawn_spot")

        flaw = DesignFlaw(location, "spot 'hal' is not declared")

        assert (flaw.location, flaw.reason) == (location, "spot 'hal' is not declared")

    def test_flaw_reads_as_location_then_reason(self) -> None:
        """DesignFlaw を文にすると「宣言の種類 '名前' 欄: 理由」の 1 行になる。"""
        flaw = DesignFlaw(DesignLocation("character", "aki", "spawn_spot"), "spot 'hal' is not declared")

        assert str(flaw) == "character 'aki' spawn_spot: spot 'hal' is not declared"

    def test_warning_keeps_location_and_reason(self) -> None:
        """DesignWarning は渡した場所と理由をそのまま持つ。"""
        location = DesignLocation("flag", "door_open", "initially_raised")

        warning = DesignWarning(location, "raised but never read")

        assert (warning.location, warning.reason) == (location, "raised but never read")

    def test_flaw_and_warning_with_the_same_contents_are_not_equal(self) -> None:
        """場所と理由が同じでも、DesignFlaw と DesignWarning は等しくない。"""
        location = DesignLocation("flag", "door_open", "initially_raised")

        assert DesignFlaw(location, "same") != DesignWarning(location, "same")
