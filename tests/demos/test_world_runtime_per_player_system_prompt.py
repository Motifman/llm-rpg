"""Issue #264 第16回実験 fix: world_runtime の per-player system prompt 統合の挙動確認。

シナリオに複数 player_spawns がある場合、各プレイヤーは「自分のペルソナ」を
埋めた system prompt を受け取る必要がある (旧実装は単一の shared system prompt
で、player 2 が「リン、〜」と自呼びする persona 混入バグになっていた)。
"""

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_LIBRARY = _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"
_MINE_VILLAGE = _REPO_ROOT / "data" / "scenarios" / "mine_village_v1.json"
_STATION_DRILL = _REPO_ROOT / "data" / "scenarios" / "station_drill.json"


class TestWorldRuntimePerPlayerSystemPrompt:
    """複数 player_spawns があるシナリオで player ごとに system prompt が変わる。"""

    def test_runtime_builds_per_player_system_prompts_when_multiple_spawns(self) -> None:
        """forbidden_library_demo は 2 spawns。runtime に 2 件の per-player prompt が入る。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        # forbidden_library_demo は 2 player スポーンを持つはず
        assert len(runtime.scenario.player_spawns) == 2
        # それぞれに per-player prompt が生成される
        assert len(runtime._world_llm_system_prompts_by_player_id) == 2

    def test_build_system_prompt_returns_player_specific_persona(self) -> None:
        """各 player の system prompt にその player の名前 (ペルソナ display name) が含まれる。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        player_ids = runtime.get_player_ids()
        # それぞれの prompt がその player の名前を含み、他の player の名前は
        # 「他者」リストとして含まれることを確認
        for pid in player_ids:
            prompt = runtime.build_system_prompt(pid)
            self_name = runtime.get_player_name(pid)
            assert self_name in prompt, f"player {pid} の prompt に自分の名前 {self_name} が含まれていない"

    def test_turn_prompt_carries_each_players_own_system_prompt(self) -> None:
        """1 ターンのプロンプトのシステムプロンプトは、そのプレイヤーの per-player prompt と同じで、相手のものとは違う。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        player_ids = runtime.get_player_ids()

        systems = [runtime.build_full_prompt(pid)["messages"][0]["content"] for pid in player_ids]

        assert systems == [runtime.build_system_prompt(pid) for pid in player_ids]
        assert systems[0] != systems[1], (
            "per-player system prompt が differentiate されていない (自呼び regression の可能性)"
        )

    def test_turn_prompt_ends_with_each_players_own_objective(self) -> None:
        """プレイヤーごとの目的 (players[].objective) を持つ廃坑の山村で、1 ターンのシステムプロンプトは per-player prompt と同じで、その人の目的で終わる。"""
        runtime = create_world_runtime(_MINE_VILLAGE)
        objective_by_player_id = {spawn.player_id: spawn.objective.strip() for spawn in runtime.scenario.player_spawns}

        for pid in runtime.get_player_ids():
            system = runtime.build_full_prompt(pid)["messages"][0]["content"]
            assert system == runtime.build_system_prompt(pid)
            assert system.endswith(f"\n\n【現在の目的】\n{objective_by_player_id[pid.value]}")
        assert len(set(objective_by_player_id.values())) > 1, "目的が全員同じだと、取り違えても通る"

    @pytest.mark.parametrize("scenario", [_MINE_VILLAGE, _STATION_DRILL])
    def test_every_player_shares_the_system_prompt_up_to_the_persona(self, scenario: Path) -> None:
        """人柄とプレイヤーごとの目的より前のシステムプロンプトは、全員で一字一句同じ。先頭が共有されてキャッシュに載る (D1630-5)。"""
        runtime = create_world_runtime(scenario)

        heads = {
            runtime.build_system_prompt(pid).partition("\n\n【ペルソナ】\n")[0] for pid in runtime.get_player_ids()
        }

        assert len(heads) == 1
        assert "【この世界の決まり】" in heads.pop()

    def test_known_people_of_each_player_do_not_contain_self(self) -> None:
        """各プレイヤーの【知っている人】には相手の名前が載り、自分の名前は他者として載らない (自呼び回帰 fix の核心)。

        Issue #264 で player 2 (リン) が「リン、〜」と speech した原因は、自分の
        名前が「他者」の一覧に入っていたため。一覧は system prompt から毎ターンの
        メッセージの【知っている人】に移った (#1520)。
        """
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        names = {pid: runtime.get_player_name(pid) for pid in runtime.get_player_ids()}
        for pid, self_name in names.items():
            known = runtime._player_acquaintances.known_people_text(pid)
            others = [n for p, n in names.items() if p != pid]
            assert all(f"- {n}" in known for n in others), known
            assert f"- {self_name}" not in known, known
