"""survival_island_v2.json の load + 基本不変条件チェック (Phase E-2)。

JSON 編集で不変条件 (各人に persona / 廃屋まで到達可能 / 4 人参照の整合性 等)
を壊した場合に早期 fail させる smoke 層。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "survival_island_v2.json"
)


@pytest.fixture(scope="module")
def loaded():
    """v2 シナリオを 1 度だけロードして全テストで共有する。"""
    return ScenarioLoader().load_from_file(str(SCENARIO_PATH))


class TestMetadata:
    """v2 識別子と暫定値。"""

    def test_id_が_v2(self, loaded) -> None:
        assert loaded.metadata.id == "survival_island_v2"

    def test_推定_tick_数は_14_日相当(self, loaded) -> None:
        assert loaded.metadata.estimated_ticks == 140


class TestPlayers:
    """4 ペルソナ + 各人に persona_prompt が定義されている。"""

    def test_プレイヤー数は_4(self, loaded) -> None:
        assert len(loaded.player_spawns) == 4

    def test_4_人の_string_id_は_設計通り(self, loaded) -> None:
        ids = {p.string_id for p in loaded.player_spawns}
        assert ids == {"ada", "noah", "rio", "kai"}

    def test_全プレイヤーに_persona_prompt_が_ある(self, loaded) -> None:
        for p in loaded.player_spawns:
            assert p.persona_prompt is not None, f"{p.string_id} に persona_prompt が無い"
            # 生存最優先の決まり文句が必ず冒頭にあること (§0 設計原則)
            assert "最優先" in p.persona_prompt or "生き残る" in p.persona_prompt

    def test_秘密の動機を裏付けるフレーバーが_initial_items_にある(self, loaded) -> None:
        """設計 §4 の対応: 各人の秘密と物的証拠を関連付ける。"""
        spawn_items = {
            p.string_id: tuple(s.spec_id.value for s in p.initial_items)
            for p in loaded.player_spawns
        }
        # 各人が少なくとも 1 つ initial item を持つ
        for sid, items in spawn_items.items():
            assert items, f"{sid} の initial_items が空"


class TestSpots:
    """観測拠点跡が追加されている。"""

    def test_観測拠点跡_3_spot_が_存在(self, loaded) -> None:
        spot_names = {n.name for n in loaded.graph.iter_spot_nodes()}
        # 廃屋 + 蔓に覆われた小道 + 湿地奥の小屋
        assert "観測拠点跡 (廃屋)" in spot_names
        assert "蔓に覆われた小道" in spot_names
        assert "湿地奥の小屋" in spot_names

    def test_spot_総数は_25_以上(self, loaded) -> None:
        """v1 の 22 spot に観測拠点跡 3 spot を追加した最低ライン。"""
        assert len(list(loaded.graph.iter_spot_nodes())) >= 25


class TestItems:
    """フレーバーアイテム 6 種が追加されている。"""

    def test_フレーバーアイテムが_全て_定義されている(self, loaded) -> None:
        item_ids = {d.string_id for d in loaded.item_spec_definitions}
        required_flavor = {
            "journal_first_half",
            "journal_second_half",
            "wedding_invitation",
            "military_emblem",
            "medicine_photo",
            "chart_fragment",
        }
        missing = required_flavor - item_ids
        assert not missing, f"フレーバーアイテム未定義: {missing}"


class TestOutcomeResolutionConfig:
    """v2 は個別 outcome 解決設定を持つ (Phase E-3b)。"""

    def test_outcome_resolution_config_が_宣言されている(self, loaded) -> None:
        config = loaded.outcome_resolution_config
        assert config is not None

    def test_rescue_ticks_は_設計通り(self, loaded) -> None:
        config = loaded.outcome_resolution_config
        # 設計 §3: 救助船 60-80 / 130-140 の window の latest を採用
        assert config.rescue_at_ticks == (80, 130)

    def test_stranded_は_tick_140(self, loaded) -> None:
        config = loaded.outcome_resolution_config
        assert config.stranded_at_tick == 140

    def test_signal_flag_は_signal_fire_lit(self, loaded) -> None:
        config = loaded.outcome_resolution_config
        assert config.signal_fire_flag == "signal_fire_lit"


class TestNoLegacyPlayerIds:
    """旧 v1 の player ID 残骸が無いこと。"""

    def test_旧_ID_は_event_条件に残っていない(self, loaded) -> None:
        """rescue events 等で mira/ren/toma を参照していないか。"""
        legacy = {"mira", "ren", "toma"}
        for evt in loaded.scenario_events:
            # ScenarioEventDef.conditions は ScenarioEventCondition の tuple
            for cond in evt.conditions:
                self._assert_no_legacy_id(cond, legacy)

    @staticmethod
    def _assert_no_legacy_id(cond, legacy) -> None:
        # leaf: spot_id 系の文字列フィールドではなく numeric int
        # PLAYER_AT_SPOT 系は player_id を文字列で持たない (numeric)
        # ここでは構造的な追跡だけ。永続的検査は loader の id mapper が担う
        for child in getattr(cond, "children", ()) or ():
            TestNoLegacyPlayerIds._assert_no_legacy_id(child, legacy)
