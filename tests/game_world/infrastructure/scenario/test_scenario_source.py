from __future__ import annotations

from pathlib import Path

from ai_rpg_world.game_world.domain.design_flaw import DesignLocation, ScenarioFile
from ai_rpg_world.game_world.infrastructure.scenario.scenario_source import read_scenario_source


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestIncludes:
    """read_scenario_source が includes: の共通の部品を、地図の鍵ごとに重ねて読むことを保証する。"""

    def test_scenario_replaces_only_the_keys_it_writes(self, tmp_path: Path) -> None:
        """共通の部品の断りの文の 1 行だけをシナリオで書き換えると、ほかの行は共通の部品のまま残る。"""
        _write(
            tmp_path,
            "common/ja.yaml",
            "refusal_texts:\n  common_rules:\n    busy: 手が離せない。\n    too_tired: 疲れた。\n",
        )
        scenario = _write(
            tmp_path,
            "mine.yaml",
            "includes: [common/ja.yaml]\nrefusal_texts:\n  common_rules:\n    busy: 今は無理だ。\n",
        )

        source = read_scenario_source(scenario)

        assert source.value == {"refusal_texts": {"common_rules": {"busy": "今は無理だ。", "too_tired": "疲れた。"}}}
        assert source.flaws == ()

    def test_later_include_overrides_earlier_include(self, tmp_path: Path) -> None:
        """後に書いた共通の部品は、前に書いた共通の部品の同じ鍵を置き換える。"""
        _write(tmp_path, "a.yaml", "rules: {name_tags: false, departed_persons_act: false}\n")
        _write(tmp_path, "b.yaml", "rules: {name_tags: true}\n")
        scenario = _write(tmp_path, "mine.yaml", "includes: [a.yaml, b.yaml]\n")

        source = read_scenario_source(scenario)

        assert source.value == {"rules": {"name_tags": True, "departed_persons_act": False}}

    def test_list_is_replaced_not_joined(self, tmp_path: Path) -> None:
        """一覧はつなげず、シナリオに書いた一覧で置き換える。"""
        _write(tmp_path, "a.yaml", "characters: {haru: {initial_items: [lamp, rope]}}\n")
        scenario = _write(tmp_path, "mine.yaml", "includes: [a.yaml]\ncharacters: {haru: {initial_items: [pick]}}\n")

        assert read_scenario_source(scenario).value == {"characters": {"haru": {"initial_items": ["pick"]}}}

    def test_missing_include_becomes_flaw_at_its_place(self, tmp_path: Path) -> None:
        """見つからない共通の部品は、includes のその位置を付けた DesignFlaw になる。"""
        scenario = _write(tmp_path, "mine.yaml", "includes: [nowhere.yaml]\n")

        assert [flaw.location for flaw in read_scenario_source(scenario).flaws] == [
            DesignLocation("world", "world", "includes[0]").in_file(ScenarioFile("mine.yaml"))
        ]

    def test_duplicated_key_in_include_is_reported_with_its_file(self, tmp_path: Path) -> None:
        """共通の部品の中の鍵の重複も DesignFlaw になり、場所にその共通の部品のファイルが付く。"""
        _write(tmp_path, "a.yaml", "rules:\n  name_tags: true\n  name_tags: false\n")
        scenario = _write(tmp_path, "mine.yaml", "includes: [a.yaml]\n")

        flaws = read_scenario_source(scenario).flaws

        assert [flaw.location for flaw in flaws] == [
            DesignLocation("world", "world", "rules.name_tags").in_file(ScenarioFile("a.yaml"))
        ]
