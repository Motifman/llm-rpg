"""survival_island_v4_coop の item usage_hint が全知の場所案内にならないことを保証する。"""

from __future__ import annotations
from tests.support.overflow_sinks import IGNORE_OVERFLOW

import json
from pathlib import Path

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "scenarios"
    / "survival_island_v4_coop.json"
)


def _load_v4():
    return ScenarioLoader().load_from_dict(json.loads(SCENARIO_PATH.read_text()))


class TestSurvivalIslandV4ItemUsageHint:
    """v4 の火まわりアイテム用途ヒントは、用途だけを示して具体場所を明かさない。"""

    def test_fire_items_have_usage_hints(self) -> None:
        """火打ち石・流木・枯れ葉には、作者定義の用途ヒントがある。"""
        scenario = _load_v4()
        by_id = {item.string_id: item for item in scenario.item_spec_definitions}

        assert by_id["flint"].usage_hint == (
            "火を起こす道具。焚き火跡や狼煙台のような火を扱う場所で interact して使う"
        )
        assert by_id["driftwood"].usage_hint == (
            "火を起こす材料。焚き火跡や狼煙台のような場所で interact の材料になる"
        )
        assert by_id["dry_leaves"].usage_hint == (
            "火を起こす材料。焚き火跡や狼煙台のような場所で interact の材料になる"
        )

    def test_fire_item_usage_hints_do_not_name_specific_spots(self) -> None:
        """用途ヒントは拠点・山頂などの具体 spot 名や内部 spot id を含まない。"""
        scenario = _load_v4()
        by_id = {item.string_id: item for item in scenario.item_spec_definitions}
        forbidden = ("拠点", "山頂", "campsite", "summit")

        for string_id in ("flint", "driftwood", "dry_leaves"):
            hint = by_id[string_id].usage_hint or ""
            for token in forbidden:
                assert token not in hint

    def test_fire_item_usage_hints_do_not_expose_internal_ids(self) -> None:
        """用途ヒントには item_spec_id / object_id / spot_id などの内部 ID を出さない。"""
        scenario = _load_v4()
        by_id = {item.string_id: item for item in scenario.item_spec_definitions}
        forbidden = (
            "item_spec_id",
            "object_id",
            "spot_id",
            "fire_pit",
            "signal_fire_pit",
        )

        for string_id in ("flint", "driftwood", "dry_leaves"):
            hint = by_id[string_id].usage_hint or ""
            for token in forbidden:
                assert token not in hint

    def test_usage_hint_does_not_derive_has_item_use_site_names(self) -> None:
        """HAS_ITEM 参照先から、特定 spot/object の名前を usage_hint へ機械導出しない。"""
        scenario = _load_v4()
        by_id = {item.string_id: item for item in scenario.item_spec_definitions}
        # v4 の HAS_ITEM では driftwood/flint が campsite の fire_pit や summit の
        # signal_fire_pit に接続されるが、D は intrinsic な用途だけを出す。
        forbidden_specific_names = ("キャンプ地", "山頂", "古い焚き火跡", "山頂の狼煙台")

        for string_id in ("flint", "driftwood", "dry_leaves"):
            hint = by_id[string_id].usage_hint or ""
            for token in forbidden_specific_names:
                assert token not in hint

    def test_fire_item_usage_hint_reaches_inventory_prompt_without_internal_ids(self) -> None:
        """v4 起動後、火打ち石の用途ヒントが所持品欄へ出て内部 ID は出ない。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        scenario = _load_v4()
        rio_id = PlayerId(scenario.id_mapper.get_int("player", "rio"))
        flint = next(item for item in scenario.item_spec_definitions if item.string_id == "flint")
        grant_item_specs_to_inventory(
            rio_id,
            (flint.spec_id,),
            runtime._item_repo,
            runtime._item_spec_repo,
            runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )
        text = runtime.build_llm_context(rio_id).current_state_text
        inventory_line = next(line for line in text.splitlines() if '"火打ち石"' in line)

        assert "火を起こす道具。焚き火跡や狼煙台のような火を扱う場所で interact して使う" in inventory_line
        for token in (
            "item_spec_id",
            "spot_id",
            "object_id",
            "flint",
            "campsite",
            "summit",
            "fire_pit",
            "signal_fire_pit",
        ):
            assert token not in inventory_line

    def test_lore_category_reaches_inventory_prompt_without_false_interact_usage(self) -> None:
        """古い徽章は LORE として表示し、存在しない interact 用途を案内しない。"""
        runtime = create_world_runtime(SCENARIO_PATH)
        scenario = _load_v4()
        noah_id = PlayerId(scenario.id_mapper.get_int("player", "noah"))
        emblem = next(
            item
            for item in scenario.item_spec_definitions
            if item.string_id == "military_emblem"
        )
        grant_item_specs_to_inventory(
            noah_id,
            (emblem.spec_id,),
            runtime._item_repo,
            runtime._item_spec_repo,
            runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )
        text = runtime.build_llm_context(noah_id).current_state_text
        inventory_line = next(line for line in text.splitlines() if '"古い徽章"' in line)

        assert "手がかり・使う物ではない" in inventory_line
        assert "食べられない" not in inventory_line
        assert "interact" not in inventory_line
