"""Issue #264 第16回実験 fix: world_runtime の per-player system prompt 統合の挙動確認。

シナリオに複数 player_spawns がある場合、各プレイヤーは「自分のペルソナ」を
埋めた system prompt を受け取る必要がある (旧実装は単一の shared system prompt
で、player 2 が「リン、〜」と自呼びする persona 混入バグになっていた)。
"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.world_runtime.default_prompt_builder_adapters import (
    WorldSystemPromptBuilder,
)
from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto


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

    def test_system_prompt_for_other_player_does_not_contain_self_as_other(self) -> None:
        """player 2 の prompt に「自分自身は他者」と書かれていない (自呼び回帰 fix の核心)。

        Issue #264 で player 2 (リン) が「リン、〜」と speech した原因は、player 1
        用に作られた prompt の participant_names に「リン」が「他者」として
        入っていたため。fix 後は player 2 の prompt では participant_names から
        自分が除外されている。
        """
        runtime = create_world_runtime(_FORBIDDEN_LIBRARY)
        player_ids = runtime.get_player_ids()
        for pid in player_ids:
            prompt = runtime.build_system_prompt(pid)
            self_name = runtime.get_player_name(pid)
            # 「同じ局面にいる者」セクション内に自分の名前が「他者」として
            # 載っていないことを確認 (heuristic: 「同じ局面にいる者」section が
            # 出ている場合のみチェック)
            if "同じ局面にいる者" in prompt:
                # 雑に判定: persona block 内 (= 自分) には登場 OK だが、
                # 「同じ局面にいる者」section 内には自分名が無いはず。
                # 完全分離は難しいので「他者リスト」を含む段落で self_name が
                # 「、」または「と」で区切られて列挙されていないことを確認
                participants_section = prompt.split("同じ局面にいる者", 1)[1].split("\n\n", 1)[0]
                # 「リン、カイト」のような自他混在パターンを検出
                assert f"{self_name}、" not in participants_section, (
                    f"player {pid} の participants に自分の名前 {self_name} が他者として記載されている"
                )
                # 単独自呼びパターン: 「{self_name}」だけ列挙される場合
                # (line stripping して比較)
                stripped = participants_section.strip()
                # 自分の名前だけが他者リストとして列挙される場合は明確な bug
                assert stripped != f"- {self_name}", (
                    f"player {pid} の participants に自分の名前 {self_name} のみ列挙されている"
                )
