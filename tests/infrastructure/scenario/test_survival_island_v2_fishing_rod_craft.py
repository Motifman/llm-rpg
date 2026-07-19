"""G2: 拠点の `crafting_log` で釣竿をクラフトできることを検証。

実験 #25 G2 問題: 釣竿は cave_inner の宝箱 (満潮 BARRIER + 鍵動作)
にしか配置されておらず、序盤に魚を取る手段が事実上閉ざされていた。
G2 対策として、`campsite` に `crafting_log` を追加し、
driftwood + vine_rope + bone_knife から釣竿を作れるようにする。

このテストは scenario JSON 上で:
- `crafting_log` object が campsite に存在
- `craft_fishing_rod` interaction が存在し、preconditions 3 件
  (bone_knife / driftwood / vine_rope) と GIVE fishing_rod 効果が
  正しく紐付いていること
を確認する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SCENARIO_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "survival_island_v2.json"
)


@pytest.fixture(scope="module")
def raw_scenario() -> dict:
    """raw JSON dict を共有 (scenario loader を経由しない素の検証)。"""
    return json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))


def _campsite(raw: dict) -> dict:
    for sp in raw["spots"]:
        if sp["id"] == "campsite":
            return sp
    raise AssertionError("campsite spot が見つからない")


def _crafting_log(raw: dict) -> dict:
    cs = _campsite(raw)
    for obj in cs["interior"]["objects"]:
        if obj["id"] == "crafting_log":
            return obj
    raise AssertionError("crafting_log object が campsite に存在しない")


class TestCraftingLogObject:
    """`crafting_log` object と craft_fishing_rod interaction の存在保証。"""

    def test_campsite_crafting_log_object(self, raw_scenario) -> None:
        """campsite に craftinglogobject が存在。"""
        cs = _campsite(raw_scenario)
        ids = [o["id"] for o in cs["interior"]["objects"]]
        assert "crafting_log" in ids

    def test_craft_fishing_rod_interaction(self, raw_scenario) -> None:
        """craftfishingrodinteraction が存在。"""
        log = _crafting_log(raw_scenario)
        action_names = [i["action_name"] for i in log["interactions"]]
        assert "craft_fishing_rod" in action_names

    def test_preconditions_bone_knife_driftwood_vine_rope_three(
        self, raw_scenario,
    ) -> None:
        """preconditions は bone knife driftwood vine rope の 3 件。"""
        log = _crafting_log(raw_scenario)
        interaction = next(
            i for i in log["interactions"] if i["action_name"] == "craft_fishing_rod"
        )
        required = {
            p["required_item"] for p in interaction["preconditions"]
            if p["condition_type"] == "HAS_ITEM"
        }
        assert required == {"bone_knife", "driftwood", "vine_rope"}

    def test_driftwood_vine_rope_fishing_rod(
        self, raw_scenario,
    ) -> None:
        """効果は driftwood と vinerope を消費し fishingrod を付与。"""
        log = _crafting_log(raw_scenario)
        interaction = next(
            i for i in log["interactions"] if i["action_name"] == "craft_fishing_rod"
        )
        removed = [
            e["parameters"]["item_spec"] for e in interaction["effects"]
            if e["effect_type"] == "REMOVE_ITEM"
        ]
        given = [
            e["parameters"]["item_spec"] for e in interaction["effects"]
            if e["effect_type"] == "GIVE_ITEM"
        ]
        assert sorted(removed) == ["driftwood", "vine_rope"]
        assert given == ["fishing_rod"]

    def test_bone_knife_not_consumed(self, raw_scenario) -> None:
        """ナイフは precondition では要求するが、消費はしない (= 道具)。"""
        log = _crafting_log(raw_scenario)
        interaction = next(
            i for i in log["interactions"] if i["action_name"] == "craft_fishing_rod"
        )
        removed = {
            e["parameters"]["item_spec"] for e in interaction["effects"]
            if e["effect_type"] == "REMOVE_ITEM"
        }
        assert "bone_knife" not in removed


class TestCampsiteDescriptionMentionsCrafting:
    """campsite description が crafting_log の存在を匂わせる (G2 hint)。"""

    def test_campsite_description_keyword_included(
        self, raw_scenario,
    ) -> None:
        """campsitedescription に加工 keyword が含まれる。"""
        cs = _campsite(raw_scenario)
        desc = cs["description"]
        # LLM が "ここで道具が作れる" と読み取れるか
        assert "加工" in desc or "削り" in desc or "道具" in desc
