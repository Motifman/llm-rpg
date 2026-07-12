"""survival_island_v2_short.json の load + 短縮タイムラインの整合チェック (P1)。

v2 のタイムラインを半分に圧縮した短縮版 (M5 の高速反復用)。機構
(outcome_resolution) だけでなく、エージェントに渡す物語文 (intro / objective) の
締め切り記述も短縮版に揃っていることを保証する — 揃っていないと「プロンプトは
3 回・8 日と言うのに機構は 2 回・4 日」という不整合でエージェントが誤った締め切りで
計画を立て、時間圧下の目標追求を観測する実験が無効になる。v2 本体を壊していない
ことも合わせて守る。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_SHORT_PATH = _SCENARIOS / "survival_island_v2_short.json"
_V2_PATH = _SCENARIOS / "survival_island_v2.json"


@pytest.fixture(scope="module")
def loaded():
    return ScenarioLoader().load_from_file(str(_SHORT_PATH))


@pytest.fixture(scope="module")
def raw() -> dict:
    with open(_SHORT_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestMetadata:
    """短縮版の識別子とタイムラインの尺。"""

    def test_id_is_v2_short(self, loaded) -> None:
        assert loaded.metadata.id == "survival_island_v2_short"

    def test_estimated_ticks_is_4_days(self, loaded) -> None:
        # 4 日 × 48 tick = 192 (v2 の 8 日 = 384 の半分)。
        assert loaded.metadata.estimated_ticks == 192

    def test_ticks_per_day_stays_48(self, loaded) -> None:
        """1 日 = 48 tick は v2 と共通 (尺だけ短くし刻みは変えない)。"""
        assert loaded.day_night_config is not None
        assert loaded.day_night_config.cycle.ticks_per_day == 48


class TestPlayersUnchanged:
    """人物設定は v2 から不変 (タイムラインだけ短縮した)。"""

    def test_four_players(self, loaded) -> None:
        assert {p.string_id for p in loaded.player_spawns} == {"ada", "noah", "rio", "kai"}

    def test_all_have_persona(self, loaded) -> None:
        for p in loaded.player_spawns:
            assert p.persona_prompt


class TestOutcomeResolution:
    """救助 2 回 (2 日目・3 日目) / 漂流確定 4 日目、に機構が縮んでいる。"""

    def test_rescue_at_two_ticks(self, loaded) -> None:
        assert loaded.outcome_resolution_config is not None
        assert loaded.outcome_resolution_config.rescue_at_ticks == (96, 144)

    def test_stranded_at_day_four(self, loaded) -> None:
        assert loaded.outcome_resolution_config.stranded_at_tick == 192

    def test_summit_and_signal_flag_unchanged(self, loaded) -> None:
        """救助の解決条件 (山頂スポット・狼煙 flag) は v2 と共通で不変。"""
        cfg = loaded.outcome_resolution_config
        assert cfg.summit_spot_id is not None
        assert cfg.signal_fire_flag == "signal_fire_lit"


class TestNarrativeTimelineConsistency:
    """物語文 (intro / objective) の締め切り記述が短縮版に揃っている。

    v2 由来の『4日目・6日目・7日目』『計3回』『8日』が残っていると、
    エージェントが誤った締め切りで計画を立てるので、それらが消えて
    短縮版の記述 (2日目・3日目 / 2回 / 4日) になっていることを保証する。
    """

    def test_intro_states_short_timeline(self, raw) -> None:
        intro = raw["metadata"]["llm_public_intro"]
        assert "4日" in intro and "計2回" in intro
        assert "8日" not in intro
        assert "計3回" not in intro

    def test_objective_states_short_rescue_days(self, raw) -> None:
        obj = raw["metadata"]["llm_objective_text"]
        assert "2日目・3日目" in obj
        assert "2 回だけ通る" in obj
        # v2 の 3 回・4/6/7 日目・8 日が残っていないこと。
        assert "4日目・6日目・7日目" not in obj
        assert "3 回だけ通る" not in obj
        assert "8 日を過ぎると" not in obj

    def test_no_stale_v2_rescue_ticks_in_events(self, raw) -> None:
        """救助船到着イベントは短縮 tick (96 / 144) だけ。v2 の 288 / 336 は無い。"""
        arrive_ticks = []
        for ev in raw["scenario_events"]:
            if str(ev.get("id", "")).startswith("rescue_ship_") and "arrive" in ev["id"]:
                for cond in ev["conditions"]:
                    if cond.get("condition_type") == "TICK_AT_LEAST":
                        arrive_ticks.append(cond["tick"])
        assert sorted(arrive_ticks) == [96, 144]


class TestV2NotModified:
    """短縮版を作っても v2 本体は不変 (過去 run との比較可能性を守る)。"""

    def test_v2_still_has_original_rescue_schedule(self) -> None:
        v2 = ScenarioLoader().load_from_file(str(_V2_PATH))
        assert v2.metadata.id == "survival_island_v2"
        assert v2.metadata.estimated_ticks == 384
        assert v2.outcome_resolution_config.rescue_at_ticks == (192, 288, 336)
        assert v2.outcome_resolution_config.stranded_at_tick == 384
