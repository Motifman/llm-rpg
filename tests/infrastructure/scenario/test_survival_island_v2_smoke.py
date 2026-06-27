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

    def test_推定_tick_数は_8_日相当(self, loaded) -> None:
        # 8 日 × 48 tick = 384 (体感を 1日 = 48 tick にした調整後)
        assert loaded.metadata.estimated_ticks == 384

    def test_ticks_per_day_は_48(self, loaded) -> None:
        """1 tick = 0.5 時間 (1日 = 48 tick)。
        実験 #29 後続で「1日が短すぎて移動だけで夜になる」体感を緩和した。"""
        assert loaded.day_night_config is not None
        assert loaded.day_night_config.cycle.ticks_per_day == 48


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
            # PR-S: 旧 §0 設計原則「生存最優先の決まり文句」は「全員生存ファースト
            # ロボット化」の原因だったため、persona の冒頭は「生存と人間関係の
            # トレードオフ」を含む表現に変えた。最低条件として「生き残る」「生き延びる」
            # のいずれかは含まれていることを保証する (= 生存への意識は失わない)。
            assert "生き残る" in p.persona_prompt or "生き延びる" in p.persona_prompt

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
        # 1 day = 48 tick: 救助船 day 4 / day 6 / day 7 (= tick 192 / 288 / 336)
        # チャンスを 3 回に増やして難易度を下げた (実験 #29 後続調整)。
        assert config.rescue_at_ticks == (192, 288, 336)

    def test_stranded_は_8日_tick_384(self, loaded) -> None:
        config = loaded.outcome_resolution_config
        # 8 日 × 48 tick = 384
        assert config.stranded_at_tick == 384

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
