"""survival_island_v3_coop.json の load + 協力ギミックの整合チェック (P12)。

v2 の地図を流用し「4 人が協力しないとクリアできない」に組み替えた協力検証版。
守るべき性質は 4 つ:

1. 点火の 2 人ゲート — light_signal は同じスポットに 2 人以上いないと実行
   できない (PLAYERS_AT_SPOT)。単独プレイでは物理的に狼煙を上げられない
2. 材料の増量 — 流木 3 / 枯れ葉 2 / 火打ち石 1。1 人でも集められるが再生
   待ちで時間が溶け、分担 + give_item が合理になる
3. 情報の分散 — 救助日程・材料の量・山頂ルートは物語文 (intro / objective)
   に書かず、世界オブジェクト (見張り台・洞窟の壁画・大樫の樹) の examine で
   得る。知識は移動せず、発話だけが運ぶ — 伝聞 (HEARSAY) の検証場
4. v2 / v2_short は不変 (過去 run との比較可能性)

3 が崩れる (物語文に日程や量が書いてある) と、情報共有の必要が消えて
協調の観測実験が無効になるため、物語文の「書いてないこと」も明示的に守る。
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


class TestMetadata:
    """協力版の識別子とタイムラインの尺 (5 日 = 240 tick)。"""

    def test_id_is_v3_coop(self, loaded) -> None:
        assert loaded.metadata.id == "survival_island_v3_coop"

    def test_estimated_ticks_is_5_days(self, loaded) -> None:
        # 5 日 × 48 tick = 240。救助 2 回 (3 日目 144 / 4 日目 192) を含む尺。
        assert loaded.metadata.estimated_ticks == 240

    def test_ticks_per_day_stays_48(self, loaded) -> None:
        """1 日 = 48 tick は v2 系と共通 (尺だけ変え、刻みは変えない)。"""
        assert loaded.day_night_config is not None
        assert loaded.day_night_config.cycle.ticks_per_day == 48


class TestPlayersUnchanged:
    """人物と初期所持品の偏り (リオ=火打ち石 / カイ=蔓ロープ) は v2 から不変。"""

    def test_four_players(self, loaded) -> None:
        assert {p.string_id for p in loaded.player_spawns} == {"ada", "noah", "rio", "kai"}

    def test_all_have_persona(self, loaded) -> None:
        for p in loaded.player_spawns:
            assert p.persona_prompt


class TestOutcomeResolution:
    """救助 2 回 (3 日目・4 日目) / 5 日目に漂流確定。"""

    def test_rescue_at_two_ticks(self, loaded) -> None:
        assert loaded.outcome_resolution_config is not None
        assert loaded.outcome_resolution_config.rescue_at_ticks == (144, 192)

    def test_stranded_at_day_five(self, loaded) -> None:
        assert loaded.outcome_resolution_config.stranded_at_tick == 240

    def test_summit_and_signal_flag_unchanged(self, loaded) -> None:
        """救助の解決条件 (山頂スポット・狼煙 flag・飢餓 2/tick) は v2 と共通。"""
        cfg = loaded.outcome_resolution_config
        assert cfg.summit_spot_id is not None
        assert cfg.signal_fire_flag == "signal_fire_lit"
        assert cfg.starvation_damage_per_tick == 2


class TestCoopGateOnSignalFire:
    """狼煙の点火は 2 人がかり + 材料増量 — 協力の唯一のハードゲート。"""

    def test_light_signal_requires_two_players_at_summit(self, raw) -> None:
        """light_signal の precondition に PLAYERS_AT_SPOT (2 人以上) がある。
        1 人では点火できない = 最低 2 人の協力がクリアの必要条件になる。"""
        inter = _find_interaction(raw, "summit", "signal_fire_pit", "light_signal")
        gates = [
            c for c in inter["preconditions"]
            if c.get("condition_type") == "PLAYERS_AT_SPOT"
        ]
        assert len(gates) == 1
        assert gates[0]["required_player_count"] == 2
        assert gates[0].get("failure_message")

    def test_light_signal_requires_bulk_materials(self, raw) -> None:
        """材料は流木 3 / 枯れ葉 2 / 火打ち石 1 (v2 の各 1 から増量)。"""
        inter = _find_interaction(raw, "summit", "signal_fire_pit", "light_signal")
        qty = {
            c["required_item"]: c.get("required_quantity", 1)
            for c in inter["preconditions"]
            if c.get("condition_type") == "HAS_ITEM"
        }
        assert qty == {"driftwood": 3, "dry_leaves": 2, "flint": 1}

    def test_light_signal_consumes_matching_quantities(self, raw) -> None:
        """点火時の消費も 3 / 2 に揃っている (火打ち石は消費しない)。"""
        inter = _find_interaction(raw, "summit", "signal_fire_pit", "light_signal")
        removed = {
            e["parameters"]["item_spec"]: e["parameters"].get("quantity", 1)
            for e in inter["effects"]
            if e["effect_type"] == "REMOVE_ITEM"
        }
        assert removed == {"driftwood": 3, "dry_leaves": 2}

    def test_two_person_requirement_is_perceivable(self, raw) -> None:
        """2 人ゲートは隠しルールではなく、狼煙台の description から読める。"""
        obj = _find_object(raw, "summit", "signal_fire_pit")
        assert "二人" in obj["description"] or "2人" in obj["description"]


class TestDistributedKnowledge:
    """情報断片が世界オブジェクトに分散している — 発話だけが知識を運ぶ。"""

    def test_oak_climb_reveals_summit_route(self, raw) -> None:
        """大樫の樹に登ると山頂ルート (川沿いの内陸チェーン) の全容が分かる。"""
        inter = _find_interaction(raw, "tall_oak", "oak_climb", "climb")
        msgs = " ".join(
            e["parameters"].get("message", "")
            for e in inter["effects"]
            if e["effect_type"] == "SHOW_MESSAGE"
        )
        for kw in ("河口", "川の上流", "高地の泉", "山麓"):
            assert kw in msgs, f"ルート断片に {kw} が無い"

    def test_lookout_reveals_rescue_schedule(self, raw) -> None:
        """崖の見張り台の scout_sea で救助船の正確な日程 (3 日目・4 日目) が分かる。"""
        inter = _find_interaction(raw, "cliff_lookout", "cliff_vantage", "scout_sea")
        msgs = " ".join(
            e["parameters"].get("message", "")
            for e in inter["effects"]
            if e["effect_type"] == "SHOW_MESSAGE"
        )
        assert "3日目" in msgs and "4日目" in msgs

    def test_cave_mural_reveals_material_quantities(self, raw) -> None:
        """洞窟の壁画で材料の必要量 (流木 3・枯れ葉 2) が分かる。"""
        inter = _find_interaction(raw, "cave_inner", "signal_mural", "examine_mural")
        msgs = " ".join(
            e["parameters"].get("message", "")
            for e in inter["effects"]
            if e["effect_type"] == "SHOW_MESSAGE"
        )
        assert "流木" in msgs and "3" in msgs and "枯れ葉" in msgs and "2" in msgs

    def test_intro_does_not_reveal_exact_schedule(self, raw) -> None:
        """intro は締め切りの存在だけ伝え、正確な日程は書かない。
        書いてしまうと見張り台の情報価値 = 共有の動機が消える。"""
        intro = raw["metadata"]["llm_public_intro"]
        assert "3日目" not in intro and "4日目" not in intro
        assert "計3回" not in intro and "8日" not in intro
        assert "5日" in intro  # 締め切りの存在は伝える

    def test_objective_does_not_reveal_quantities_or_route(self, raw) -> None:
        """objective は「狼煙 3 種 + 山頂」の基本方針のみ。量・日程・ルートは
        世界の断片へ分散済みで、ここに書かない。"""
        obj = raw["metadata"]["llm_objective_text"]
        assert "狼煙" in obj and "山頂" in obj
        assert "3日目" not in obj and "4日目" not in obj
        assert "流木 3" not in obj and "流木3" not in obj
        assert "高地の泉" not in obj

    def test_coastal_spots_hint_inland_gradient(self, raw) -> None:
        """v2 の欠陥 (沿岸に内陸ヒントゼロ) の修正: 浜の記述に川→内陸の
        弱い勾配ヒントがある (正解ルートそのものは書かない)。"""
        beach = _find_spot(raw, "shipwreck_beach")
        campsite = _find_spot(raw, "campsite")
        combined = beach["description"] + campsite["description"]
        assert "川" in combined
        assert "高地の泉" not in combined  # 正解の具体名は出さない


class TestNarrativeTimelineConsistency:
    """救助船イベントの tick が新スケジュール (144 / 192) に揃っている。"""

    def test_arrive_events_match_new_schedule(self, raw) -> None:
        arrive_ticks = []
        for ev in raw["scenario_events"]:
            if str(ev.get("id", "")).startswith("rescue_ship_") and "arrive" in ev["id"]:
                for cond in ev["conditions"]:
                    if cond.get("condition_type") == "TICK_AT_LEAST":
                        arrive_ticks.append(cond["tick"])
        assert sorted(arrive_ticks) == [144, 192]

    def test_no_stale_v2_event_ticks(self, raw) -> None:
        """v2 の 288 / 336 の救助イベントが残っていない。"""
        text = json.dumps(raw["scenario_events"])
        assert '"tick": 288' not in text and '"tick": 336' not in text


class TestBaseScenariosNotModified:
    """v3 を作っても v2 / v2_short は不変 (過去 run との比較可能性を守る)。"""

    def test_v2_unchanged(self) -> None:
        v2 = ScenarioLoader().load_from_file(str(_V2_PATH))
        assert v2.metadata.estimated_ticks == 384
        assert v2.outcome_resolution_config.rescue_at_ticks == (192, 288, 336)

    def test_v2_short_unchanged(self) -> None:
        short = ScenarioLoader().load_from_file(str(_V2_SHORT_PATH))
        assert short.metadata.estimated_ticks == 192
        assert short.outcome_resolution_config.rescue_at_ticks == (96, 144)
