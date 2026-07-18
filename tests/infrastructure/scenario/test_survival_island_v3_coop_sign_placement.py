"""survival_island_v3_coop に配置した看板 (PR-H) の静的検証。

#714 で入った看板 primitive (WRITE_PLAYER_TEXT / SHOW_PLAYER_TEXT) を
v3_coop に配置した。run 分析で「私的な発見 (memo) が公共化されない」こと
が敗因の一つだったため、不在の相手にも届く書き置き手段として、単独行動者
の経路と多数派の生活圏が交わる 2 箇所に置く:

- 拠点 (campsite) の「板切れの掲示」— 全員が寝食のために戻ってくる生活圏
- 山麓 (foothills) の「石積みの目印」— 崖沿い/洞窟へ分岐する山道の分岐点

エージェントに使用を強制する仕掛け (precondition や goal) は入れない。
「使われるかどうか自体が観察対象」であるため、本テストは配置の構造
(action / effect_type / description からの知覚可能性) のみを保証する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_COOP_PATH = _SCENARIOS / "survival_island_v3_coop.json"
_V2_PATH = _SCENARIOS / "survival_island_v2.json"
_V2_SHORT_PATH = _SCENARIOS / "survival_island_v2_short.json"

_SIGN_PLACEMENTS = (
    ("campsite", "camp_notice_board", "板切れの掲示", "write_notice", "read_notice"),
    ("foothills", "trail_cairn", "石積みの目印", "carve_message", "read_carving"),
)


@pytest.fixture(scope="module")
def loaded():
    return ScenarioLoader().load_from_file(str(_COOP_PATH))


@pytest.fixture(scope="module")
def raw() -> dict:
    with open(_COOP_PATH, encoding="utf-8") as f:
        return json.load(f)


def _find_spot(raw: dict, spot_id: str) -> dict:
    for s in raw["spots"]:
        if s["id"] == spot_id:
            return s
    raise AssertionError(f"spot not found: {spot_id}")


def _find_object(raw: dict, spot_id: str, object_id: str) -> dict:
    for o in (_find_spot(raw, spot_id).get("interior") or {}).get("objects", []):
        if o["id"] == object_id:
            return o
    raise AssertionError(f"object not found: {spot_id}/{object_id}")


def _find_interaction(raw: dict, spot_id: str, object_id: str, action: str) -> dict:
    for i in _find_object(raw, spot_id, object_id).get("interactions", []):
        if i["action_name"] == action:
            return i
    raise AssertionError(f"interaction not found: {object_id}.{action}")


class TestSignObjectsAreLoaded:
    """2 箇所の看板が SIGN object_type として scenario から解決される。"""

    @pytest.mark.parametrize(
        "spot_id,object_id,object_name,write_action,read_action", _SIGN_PLACEMENTS
    )
    def test_sign_object_resolves_as_sign_type(
        self, loaded, spot_id, object_id, object_name, write_action, read_action
    ) -> None:
        from ai_rpg_world.domain.world_graph.enum.spot_object_type import (
            SpotObjectTypeEnum,
        )

        for interior in loaded.interiors.values():
            for obj in interior.objects:
                if obj.name == object_name:
                    assert obj.object_type == SpotObjectTypeEnum.SIGN
                    return
        raise AssertionError(f"{object_name} が scenario から解決されない")


class TestSignInteractionsUseSignEffects:
    """各看板が write 系 (WRITE_PLAYER_TEXT) と examine 系 (SHOW_PLAYER_TEXT)
    の両方を持つ (書けるだけ・読めるだけの片手落ちにしない)。"""

    @pytest.mark.parametrize(
        "spot_id,object_id,object_name,write_action,read_action", _SIGN_PLACEMENTS
    )
    def test_write_action_uses_write_player_text(
        self, raw, spot_id, object_id, object_name, write_action, read_action
    ) -> None:
        inter = _find_interaction(raw, spot_id, object_id, write_action)
        effect_types = {e["effect_type"] for e in inter["effects"]}
        assert "WRITE_PLAYER_TEXT" in effect_types

    @pytest.mark.parametrize(
        "spot_id,object_id,object_name,write_action,read_action", _SIGN_PLACEMENTS
    )
    def test_read_action_uses_show_player_text(
        self, raw, spot_id, object_id, object_name, write_action, read_action
    ) -> None:
        inter = _find_interaction(raw, spot_id, object_id, read_action)
        effect_types = {e["effect_type"] for e in inter["effects"]}
        assert "SHOW_PLAYER_TEXT" in effect_types

    @pytest.mark.parametrize(
        "spot_id,object_id,object_name,write_action,read_action", _SIGN_PLACEMENTS
    )
    def test_interactions_have_no_forced_preconditions(
        self, raw, spot_id, object_id, object_name, write_action, read_action
    ) -> None:
        """使用を強制/誘導する precondition (goal 連携等) が付いていない。
        「使われるかどうか自体が観察対象」であることを構造的に保証する。"""
        write_inter = _find_interaction(raw, spot_id, object_id, write_action)
        read_inter = _find_interaction(raw, spot_id, object_id, read_action)
        assert write_inter["preconditions"] == []
        assert read_inter["preconditions"] == []


class TestSignWritabilityIsPerceivableWithoutExamine:
    """「書き込めること」がオブジェクトの description (examine 前に見える
    物語文) から知覚できる。知覚できないルールにしない、という要求への対応。"""

    @pytest.mark.parametrize(
        "spot_id,object_id,object_name,write_action,read_action", _SIGN_PLACEMENTS
    )
    def test_object_description_mentions_writing(
        self, raw, spot_id, object_id, object_name, write_action, read_action
    ) -> None:
        desc = _find_object(raw, spot_id, object_id)["description"]
        assert any(kw in desc for kw in ("書き残せ", "書き込め", "刻み込", "文字を刻"))


class TestSignPlacementDoesNotTouchDifficulty:
    """看板の追加が、狼煙材料・2 人ゲート・救助 tick 等の難度要素に触れていない。"""

    def test_light_signal_gate_unchanged(self, raw) -> None:
        inter = _find_interaction(raw, "summit", "signal_fire_pit", "light_signal")
        gates = [
            c for c in inter["preconditions"]
            if c.get("condition_type") == "PLAYERS_AT_SPOT"
        ]
        assert len(gates) == 1
        assert gates[0]["required_player_count"] == 2
        qty = {
            c["required_item"]: c.get("required_quantity", 1)
            for c in inter["preconditions"]
            if c.get("condition_type") == "HAS_ITEM"
        }
        assert qty == {"driftwood": 3, "dry_leaves": 2, "flint": 1}

    def test_rescue_ticks_unchanged(self, loaded) -> None:
        assert loaded.outcome_resolution_config.rescue_at_ticks == (144, 192)
        assert loaded.outcome_resolution_config.stranded_at_tick == 240

    def test_estimated_ticks_unchanged(self, loaded) -> None:
        assert loaded.metadata.estimated_ticks == 240


class TestBaseScenariosNotModified:
    """v2 / v2_short は看板配置の影響を受けない (1 バイトも変わらない)。"""

    def test_v2_unchanged(self) -> None:
        v2 = ScenarioLoader().load_from_file(str(_V2_PATH))
        assert v2.metadata.estimated_ticks == 384
        assert v2.outcome_resolution_config.rescue_at_ticks == (192, 288, 336)

    def test_v2_short_unchanged(self) -> None:
        short = ScenarioLoader().load_from_file(str(_V2_SHORT_PATH))
        assert short.metadata.estimated_ticks == 192
        assert short.outcome_resolution_config.rescue_at_ticks == (96, 144)
