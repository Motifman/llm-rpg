from __future__ import annotations

import importlib
import pkgutil
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from ai_rpg_world.game_world.domain import exception as game_world_exception
from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusalKind
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException
from ai_rpg_world.game_world.domain.people._person_placeholders import person_placeholders_in
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import Capacity, HitPoints
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario, load_scenario
from ai_rpg_world.game_world.infrastructure.scenario.yaml_document import read_yaml_document

_COMMON = Path(__file__).parents[4] / "data" / "scenarios" / "common" / "ja_default.yaml"

_PEOPLE = frozenset({"actor", "target", "chosen_by_group", "each_person"})
_PLACEHOLDERS_BY_BUILT_IN_ACTION = {
    "travel": frozenset({"actor", "destination"}),
    "speak": frozenset({"actor", "speech"}),
    "hand_over": frozenset({"actor", "item", "target"}),
    "tend": frozenset({"actor", "target"}),
    "pick_up": frozenset({"actor", "item"}),
    "drop": frozenset({"actor", "item"}),
    "use_item": frozenset({"actor", "item"}),
    "hold": frozenset({"actor", "item"}),
    "put_away": frozenset({"actor", "item"}),
    "listen": frozenset({"actor"}),
    "wait": frozenset({"actor"}),
    "search": frozenset({"actor"}),
    "cast_ballot": frozenset({"actor"}),
}

_BUILT_IN_ACTIONS = frozenset(
    {
        ActionKind.TRAVEL,
        ActionKind.SPEAK,
        ActionKind.LISTEN,
        ActionKind.WAIT,
        ActionKind.TEND,
        ActionKind.HAND_OVER,
        ActionKind.PICK_UP,
        ActionKind.DROP,
        ActionKind.SEARCH,
        ActionKind.USE_ITEM,
        ActionKind.HOLD,
        ActionKind.PUT_AWAY,
        ActionKind.CAST_BALLOT,
    }
)

_SMALLEST_SCENARIO = """
includes: [common/ja_default.yaml]
introduction:
  text: 坑道の奥で目を覚ました。
  objective: 外へ出る。
spots:
  tunnel:
    name: 坑道
    description: 狭い坑道。
    atmosphere: { lighting: dark }
characters:
  haru: { appearance: 年かさの男, spawn_spot: tunnel }
ending:
  ends_when: all_outcomes_decided
time:
  day_night: null
  weather: null
"""


def _common() -> dict[object, object]:
    document = read_yaml_document(_COMMON.read_text(encoding="utf-8"))
    assert document.flaws == ()
    assert isinstance(document.value, dict)
    return document.value


def _load_smallest_scenario(tmp_path: Path) -> LoadedScenario:
    (tmp_path / "common").mkdir()
    shutil.copy(_COMMON, tmp_path / "common" / "ja_default.yaml")
    scenario = tmp_path / "mine.yaml"
    scenario.write_text(_SMALLEST_SCENARIO, encoding="utf-8")
    return load_scenario(scenario)


def _texts(value: object, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _texts(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _texts(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _error_codes() -> frozenset[str]:
    for module in pkgutil.iter_modules(game_world_exception.__path__):
        importlib.import_module(f"{game_world_exception.__name__}.{module.name}")
    codes: set[str] = set()
    pending: list[type[GameWorldDomainException]] = [GameWorldDomainException]
    while pending:
        cls = pending.pop()
        codes.add(cls.error_code)
        pending.extend(cls.__subclasses__())
    return frozenset(codes)


class TestCommonJaDefaultReads:
    """共通の部品 ja_default.yaml が、読み込み処理にそのまま通ることを保証する。"""

    def test_common_part_is_readable_as_yaml(self) -> None:
        """ja_default.yaml は YAML として読め、鍵の重複などの DesignFlaw を持たない。"""
        common = _common()

        assert set(common) == {
            "rules",
            "refusal_texts",
            "built_in_action_perceptions",
            "perception_defaults",
            "defaults",
        }

    def test_smallest_scenario_including_it_loads_without_flaws(self, tmp_path: Path) -> None:
        """場所 1 つと人 1 人だけを書いたシナリオが ja_default.yaml を取り込むと、DesignFlaw を出さずに設計図になり、人は体力 100・荷 20 で始まる。"""
        (haru,) = _load_smallest_scenario(tmp_path).design.initial_world().people

        assert (haru.hp, haru.pack_capacity) == (HitPoints(100, 100), Capacity(20))


class TestRefusalTexts:
    """ja_default.yaml の断りの文の表が、共通の決まりをすべて持ち、集約の断りの鍵が実在する error_code であることを保証する。"""

    def test_common_rule_texts_cover_every_kind(self, tmp_path: Path) -> None:
        """共通の決まりの断りの文は、CommonRuleRefusalKind のすべての種類を持つ。"""
        texts = _load_smallest_scenario(tmp_path).design.refusal_texts

        assert set(texts.common_rules) == set(CommonRuleRefusalKind)

    def test_world_state_texts_name_existing_error_codes(self) -> None:
        """集約の断りの文の鍵は、どれも game_world のドメイン例外の error_code にある (綴り違いの鍵は使われない)。"""
        written = set(_common()["refusal_texts"]["world_state"])  # type: ignore[index]

        assert written - _error_codes() == set()


class TestBuiltInActionPerceptions:
    """ja_default.yaml の組み込みの行為の知覚の文が、世界で行える組み込みの行為をすべて持つことを保証する。"""

    def test_every_built_in_action_has_its_perception(self, tmp_path: Path) -> None:
        """移動・話す・耳を澄ます・待つ・介抱・渡す・拾う・置く・探す・品物を使う・持ち替え・投票の知覚の文がある。"""
        perceptions = _load_smallest_scenario(tmp_path).design.built_in_action_perceptions

        assert set(perceptions.by_kind) == _BUILT_IN_ACTIONS


class TestPlaceholders:
    """ja_default.yaml の文の中のプレースホルダーが、決まった名前だけであることを保証する。"""

    @pytest.mark.parametrize("section", ["refusal_texts", "perception_defaults", "defaults", "rules"])
    def test_texts_name_only_people(self, section: str) -> None:
        """組み込みの行為の知覚の文のほかは、人のプレースホルダー actor・target・chosen_by_group・each_person しか書かない。"""
        unknown = {
            path: sorted(person_placeholders_in(text) - _PEOPLE)
            for path, text in _texts(_common()[section], section)
            if person_placeholders_in(text) - _PEOPLE
        }

        assert unknown == {}

    @pytest.mark.parametrize("action", sorted(_PLACEHOLDERS_BY_BUILT_IN_ACTION))
    def test_built_in_action_texts_name_only_what_the_action_fills(self, action: str) -> None:
        """組み込みの行為の知覚の文は、scenario_format.md の表でその行為に載せたプレースホルダーだけを書く (拾うなら actor と item)。"""
        perception = _common()["built_in_action_perceptions"][action]  # type: ignore[index]
        unknown = {
            path: sorted(person_placeholders_in(text) - _PLACEHOLDERS_BY_BUILT_IN_ACTION[action])
            for path, text in _texts(perception, action)
            if person_placeholders_in(text) - _PLACEHOLDERS_BY_BUILT_IN_ACTION[action]
        }

        assert unknown == {}
