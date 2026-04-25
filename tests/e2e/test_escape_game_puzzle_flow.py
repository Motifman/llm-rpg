"""脱出ゲーム E2E テスト — パズルフロー全体を検証する。

ScenarioLoader → EscapeGameRuntime → 正解ルート実行 → WIN 判定 を通しで確認。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "abandoned_hospital.json"


def _create_runtime():
    from demos.escape_game.escape_game_runtime import create_escape_game_runtime
    return create_escape_game_runtime(SCENARIO_PATH)


class TestEscapeGameScenarioLoad:
    def test_runtime_creation_succeeds(self) -> None:
        runtime = _create_runtime()
        assert runtime.metadata.id == "abandoned_hospital"

    def test_players_are_placed_on_graph(self) -> None:
        runtime = _create_runtime()
        for pid_cfg in runtime.scenario.player_spawns:
            pid = PlayerId(pid_cfg.player_id)
            obs = runtime.build_observation(pid)
            assert "現在地:" in obs

    def test_initial_observation_contains_spot_name(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
        obs = runtime.build_observation(p1)
        assert "エントランスホール" in obs

    def test_initial_available_tools_non_empty(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
        tools = runtime.build_available_tools(p1)
        assert "spot_graph_travel_to" in tools
        assert "spot_graph_explore" in tools
        assert "memory_query" in tools
        assert "memory_working_memory_append" in tools

    def test_system_prompt_is_character_aware_and_non_spoiler(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
        prompt = runtime.build_system_prompt(p1)
        assert "ペルソナ" in prompt or "【ペルソナ】" in prompt
        assert "静原" in prompt or "廃墟" in prompt
        assert "150ティック" not in prompt
        assert "150 ティック" not in prompt
        # 生の metadata.description（ネタバレ全文）は渡さない
        assert "記憶を切除" not in prompt and "再編" not in prompt

    def test_full_prompt_has_escape_sections(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
        full = runtime.build_full_prompt(p1)
        assert "【現在の目的】" in full["user"]
        assert "【発見済み証拠" in full["user"]
        assert "【未解決の仮説" in full["user"]
        assert "【関連する記憶" in full["user"]

    def test_tick_limit_yields_lose(self) -> None:
        runtime = _create_runtime()
        for _ in range(150):
            runtime.advance_tick()

        end = runtime.check_game_end()
        assert end.is_ended is True
        assert end.result == GameResultEnum.LOSE


@pytest.mark.skip(
    reason="abandoned_hospital シナリオは単一プレイヤー・グラフ再設計済みのため旧ルートは無効"
)
class TestEscapeGameFullPuzzleFlow:
    """正解ルートを完走して WIN になることを検証する。"""

    def test_complete_escape_yields_win(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
        p2 = PlayerId(runtime.scenario.player_spawns[1].player_id)

        runtime.advance_tick()
        runtime.do_interact(p1, "reception_desk", "search")

        runtime.advance_tick()
        runtime.do_move(p1, "dim_corridor")

        runtime.advance_tick()
        runtime.do_interact(p1, "nurse_desk", "search")

        runtime.advance_tick()
        runtime.do_move(p1, "directors_office")

        runtime.advance_tick()
        runtime.do_interact(p1, "directors_desk", "examine")

        runtime.advance_tick()
        runtime.do_interact(p1, "office_safe", "open")

        runtime.advance_tick()
        runtime.do_move(p2, "operating_room")

        runtime.advance_tick()
        runtime.do_interact(p2, "instrument_shelf", "search")

        runtime.advance_tick()
        runtime.do_move(p2, "basement")

        runtime.advance_tick()
        runtime.do_interact(p2, "wall_crack", "cut_open")

        runtime.advance_tick()
        runtime.do_move(p1, "emergency_exit")

        runtime.advance_tick()
        runtime.do_move(p2, "hidden_passage")
        runtime.do_move(p2, "emergency_exit")

        runtime.advance_tick()
        runtime.do_interact(p1, "emergency_door", "unlock")

        runtime.advance_tick()
        runtime.do_move(p1, "outside")
        runtime.do_move(p2, "outside")

        end = runtime.check_game_end()
        assert end.is_ended is True
        assert end.result == GameResultEnum.WIN


@pytest.mark.skip(
    reason="旧スポットID前提の前提検証。新シナリオでは別途ドメインテストを追加予定"
)
class TestInteractionPreconditions:
    """条件未達成でのインタラクション失敗を検証する。

    ドメインサービスは precondition 不成立時に InteractionNotAllowedException を投げる。
    """

    def test_safe_requires_diary_flag(self) -> None:
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)

        runtime.do_interact(p1, "reception_desk", "search")
        runtime.do_move(p1, "dim_corridor")
        runtime.do_interact(p1, "nurse_desk", "search")
        runtime.do_move(p1, "directors_office")

        with pytest.raises(InteractionNotAllowedException, match="手がかり|わからない"):
            runtime.do_interact(p1, "office_safe", "open")

    def test_wall_crack_requires_scalpel(self) -> None:
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )
        runtime = _create_runtime()
        p2 = PlayerId(runtime.scenario.player_spawns[1].player_id)

        runtime.do_move(p2, "basement")
        with pytest.raises(InteractionNotAllowedException, match="鋭い|必要"):
            runtime.do_interact(p2, "wall_crack", "cut_open")

    def test_emergency_door_requires_key(self) -> None:
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )
        runtime = _create_runtime()
        p2 = PlayerId(runtime.scenario.player_spawns[1].player_id)

        runtime.do_move(p2, "emergency_exit")
        with pytest.raises(InteractionNotAllowedException, match="鍵|錠前"):
            runtime.do_interact(p2, "emergency_door", "unlock")


@pytest.mark.skip(reason="旧シナリオの代替ルート")
class TestAlternativeRoute:
    """腐食剤ルートを検証する。"""

    def test_reagent_can_open_emergency_door(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)

        runtime.do_interact(p1, "reception_desk", "search")
        runtime.do_move(p1, "dim_corridor")
        runtime.do_move(p1, "operating_room")
        runtime.do_interact(p1, "chemical_cabinet", "take")

        runtime.do_move(p1, "dim_corridor")
        runtime.do_move(p1, "emergency_exit")
        result = runtime.do_interact(p1, "emergency_door", "use_reagent")
        assert any("腐食" in m or "溶け" in m or "崩れ" in m for m in result.messages)


class TestExploration:
    """探索（discoverable_items）の検証。"""

    def test_repeated_explore_runs_without_error(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)

        result1 = runtime.do_explore(p1)
        result2 = runtime.do_explore(p1)
        assert result1 is not None and result2 is not None


class TestObservationUpdates:
    """アクション後の観測が正しく更新されることを検証する。"""

    def test_spot_changes_after_move(self) -> None:
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)

        obs1 = runtime.build_observation(p1)
        assert "エントランスホール" in obs1

        # 接続先はシナリオに依存（最初の通行可能接続の string id を使用）
        ctx = runtime.build_llm_context(p1)
        labels = [
            lbl
            for lbl, t in ctx.tool_runtime_context.targets.items()
            if getattr(t, "spot_id", None) is not None
        ]
        assert labels, "移動先ラベルが無い"
        dest_label = labels[0]
        dest = ctx.tool_runtime_context.targets[dest_label]
        dest_str = runtime.id_mapper.get_str("spot", dest.spot_id)
        runtime.do_move(p1, dest_str)
        obs2 = runtime.build_observation(p1)
        assert obs2 != obs1

    @pytest.mark.skip(reason="旧2人プレイ前提の通行検証")
    def test_connection_passability_updates_after_interaction(self) -> None:
        """亀裂を切り開くと接続先が通行可に変わることを検証する。"""
        runtime = _create_runtime()
        p2 = PlayerId(runtime.scenario.player_spawns[1].player_id)

        runtime.do_move(p2, "operating_room")
        runtime.do_interact(p2, "instrument_shelf", "search")
        runtime.do_move(p2, "basement")

        obs_before = runtime.build_observation(p2)
        assert "通行不可" in obs_before

        runtime.do_interact(p2, "wall_crack", "cut_open")
        obs_after = runtime.build_observation(p2)
        assert "隠し通路" in obs_after

    def test_label_mapping_contains_ids(self) -> None:
        """UiContext の targets にラベル→ID マッピングが存在する。"""
        runtime = _create_runtime()
        p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
        ctx = runtime.build_llm_context(p1)
        targets = ctx.tool_runtime_context.targets
        assert len(targets) > 0
        for label, target in targets.items():
            assert label == target.label
