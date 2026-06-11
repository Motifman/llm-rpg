"""#356 後続: モンスター名 fallback の漏出を検知する。

実験 #25 OFF trace で `monster_attacked_player` 観測 13 件すべてが
「**何かのモンスター**に襲われ 5 のダメージを受けた」になっていた。

原因: `escape_game_runtime` で `ObservationFormatter` を構築する際に
`monster_repository` を渡しておらず、`ObservationNameResolver` が
`FALLBACK_MONSTER_LABEL` (=「何かのモンスター」) を常に返していた。

修正後は monster_placements のあるシナリオで monster_repository が
注入され、template name (e.g. 「野犬」) が prose に乗る。
"""

from __future__ import annotations

from pathlib import Path

import pytest


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "survival_island_v2.json"
)


class TestObservationFormatterMonsterNameWiring:
    """`create_escape_game_runtime` が monster_repository を formatter に渡す。"""

    def test_v2_の_obs_formatter_に_monster_repository_が_注入される(self) -> None:
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

        runtime = create_escape_game_runtime(SCENARIO_PATH)
        # 観測経路は LlmTurn セッション側に持っているが、runtime._obs_pipeline
        # 自身が ObservationFormatter を握っている。
        pipeline = runtime._obs_pipeline
        formatter = pipeline._formatter
        # name resolver の _monster_repository が None でない (= 注入されている)
        assert formatter._name_resolver._monster_repository is not None, (
            "monster_repository が ObservationFormatter に渡っていない。"
            "monster_name は FALLBACK_MONSTER_LABEL (何かのモンスター) に化ける"
        )

    def test_monster_name_lookup_で_template_名が_引ける(self) -> None:
        """name_resolver.monster_name_by_monster_id が「野犬」等の実名を返す。"""
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

        runtime = create_escape_game_runtime(SCENARIO_PATH)
        # シナリオ起動時に少なくとも feral_dog @ plane_wreck が spawn される
        graph = runtime._spot_graph_repo.find_graph()
        all_monster_ids = []
        for n in graph.iter_spot_nodes():
            for mid in graph.monster_presence_at(n.spot_id).present_monster_ids:
                all_monster_ids.append(mid)
        assert all_monster_ids, "シナリオが monster を spawn していない"

        formatter = runtime._obs_pipeline._formatter
        resolver = formatter._name_resolver
        # 各 monster の名前を resolve し、fallback ではなく実名が返ることを確認
        from ai_rpg_world.application.observation.services.formatters.name_resolver import (
            FALLBACK_MONSTER_LABEL,
        )
        for mid in all_monster_ids:
            name = resolver.monster_name_by_monster_id(mid)
            assert name != FALLBACK_MONSTER_LABEL, (
                f"monster {mid} の名前が fallback ({FALLBACK_MONSTER_LABEL}) のまま。"
                f"monster_repository から template を引けていない"
            )
            assert name, "monster name が空文字"


class TestForbiddenLibraryNoRegression:
    """monster を持たないシナリオでも正常に起動する (回帰防止)。"""

    def test_forbidden_library_demo_は_monster_repository_None_で_OK(self) -> None:
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

        scenario_path = SCENARIO_PATH.parent / "forbidden_library_demo.json"
        runtime = create_escape_game_runtime(scenario_path)
        formatter = runtime._obs_pipeline._formatter
        # monster_placements が無いシナリオでは None のまま (現状の設計)
        # NOTE: 万一現状の挙動が「常に渡す」に変わってもこのテストは緩和して OK
        # ここでは「formatter 構築自体が例外なく完了する」が必要十分。
        assert formatter is not None
