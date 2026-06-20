"""``single_relic_contention_demo`` シナリオの読み込み + 競合解決の挙動検証。

intent キューの「同 tick で同じ対象に挑むと敗者は失敗観測を受け取る」を
最小構成で可視化するためのデモシナリオ。本テストでは:

- 2 人のプレイヤーが同じ部屋にスポーンすること
- 単一遺物の interactions に claim アクションがあり前提条件が物体状態であること
- 先に claim した側は成功、後に claim した側は precondition 違反で失敗すること
- 成功時に win フラグ ``relic_claimed`` が立つこと

を runtime 経由で確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "single_relic_contention_demo.json"
)


@pytest.fixture
def runtime():
    """world_runtime にシナリオをロードして返す。"""
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    return create_world_runtime(SCENARIO_PATH)


class TestSingleRelicContentionDemoScenarioLoad:
    """シナリオ構造の検証。"""

    def test_scenario_loads_with_two_players(self, runtime) -> None:
        """2 体のプレイヤーがスポーンする (intent キュー競合の前提)。"""
        player_ids = [p.value for p in runtime.get_player_ids()]
        assert sorted(player_ids) == [1, 2]

    def test_both_players_spawn_in_altar_room(self, runtime) -> None:
        """両プレイヤーが同じ部屋 (altar_room) に居る。"""
        graph = runtime._spot_graph_repo.find_graph()
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        spot_a = graph.get_entity_spot(EntityId.create(1))
        spot_b = graph.get_entity_spot(EntityId.create(2))
        assert spot_a == spot_b
        # スポット名で確認
        spot_node = graph.get_spot(spot_a)
        assert spot_node.name == "祭壇の間"

    def test_metadata_has_tick_limit_and_win_flag(self, runtime) -> None:
        """game_end: win=FLAG_SET / lose=TICK_LIMIT が読まれている。"""
        scenario = runtime.scenario
        assert len(scenario.win_conditions) == 1
        assert len(scenario.lose_conditions) == 1
        win = scenario.win_conditions[0]
        lose = scenario.lose_conditions[0]
        # 列挙値か文字列のどちらかで一致
        assert win.condition_type.value == "FLAG_SET"
        assert win.target_flag == "relic_claimed"
        assert lose.condition_type.value == "TICK_LIMIT"
        assert lose.tick_limit == 30


class TestSingleRelicContentionResolution:
    """同一遺物への 2 連続アクションで先勝・後敗が確定する挙動。"""

    def test_first_claim_succeeds_and_triggers_win_end(self, runtime) -> None:
        """先に claim した側は成功し relic_claimed フラグが立ち、ゲームが WIN で終了する。"""
        # ゲーム開始前は終了していない
        assert runtime.check_game_end().is_ended is False

        # Player 1 が claim
        result = runtime.do_interact(PlayerId(1), "ancient_relic", "claim")
        combined = " ".join(result.messages or [])
        # 成功時のメッセージ (SHOW_MESSAGE effect 由来) が乗る
        assert "光を放ち" in combined or "記録が刻まれた" in combined, (
            f"expected success-path message, got: {result.messages}"
        )
        # 失敗 precondition のメッセージは載らない
        assert "失っている" not in combined

        # ゲーム終了判定 (win フラグ relic_claimed が立った)
        end_result = runtime.check_game_end()
        assert end_result.is_ended is True

    def test_second_claim_raises_interaction_not_allowed(self, runtime) -> None:
        """2 番目に claim を試みた側は precondition 違反で
        ``InteractionNotAllowedException`` を投げる。

        ドメイン層は失敗を例外で表現する。アプリケーション層 (LLM 経路) では
        ``_WorldLlmWiring._execute_tool`` の外側 try/except がこれを捕捉し、
        ``success=False`` の DTO に変換する。intent キュー導入後はこの失敗 DTO を
        ``ActionFailedObservationEmitter`` が ``type: action_failed`` 観測として
        敗者に届ける (B-1 wiring 後に統合確認)。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        # Player 1 が先に成功
        runtime.do_interact(PlayerId(1), "ancient_relic", "claim")

        # Player 2 が後追いで claim → 例外
        with pytest.raises(InteractionNotAllowedException) as excinfo:
            runtime.do_interact(PlayerId(2), "ancient_relic", "claim")
        # シナリオで定義した failure_message が例外メッセージに反映される
        assert "失っている" in str(excinfo.value)
