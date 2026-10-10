"""Issue #264 第16回実験 fix: world_runtime の per-player system prompt 統合の挙動確認。

シナリオに複数 player_spawns がある場合、各プレイヤーは「自分のペルソナ」を
埋めた system prompt を受け取る必要がある (旧実装は単一の shared system prompt
で、player 2 が「リン、〜」と自呼びする persona 混入バグになっていた)。
"""

from pathlib import Path

from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.world_runtime.default_prompt_builder_adapters import (
    WorldSystemPromptBuilder,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_LIBRARY = (
    _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"
)


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
            assert self_name in prompt, (
                f"player {pid} の prompt に自分の名前 {self_name} が含まれていない"
            )

    def test_system_prompt_builder_adapter_returns_per_player_prompt(self) -> None:
        """WorldSystemPromptBuilder.build() が player_info.player_name から
        正しい per-player prompt を引く。"""
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        builder = WorldSystemPromptBuilder(runtime)
        player_ids = runtime.get_player_ids()

        # 各 player の prompt を取得し、別 player の prompt と異なることを確認
        prompts: dict[str, str] = {}
        for pid in player_ids:
            name = runtime.get_player_name(pid)
            info = SystemPromptPlayerInfoDto(
                player_name=name,
                role="adventurer",
                race="human",
                element="fire",
                game_description="",
            )
            prompts[name] = builder.build(info)

        names = list(prompts.keys())
        assert len(names) == 2
        # 2 つの prompt が異なる (per-player persona が効いている)
        assert prompts[names[0]] != prompts[names[1]], (
            "per-player system prompt が differentiate されていない (自呼び regression の可能性)"
        )

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
