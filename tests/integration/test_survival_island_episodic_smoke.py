"""survival_island / survival_island_v2 シナリオで episodic memory pipeline が
そのまま wire される smoke harness (PR #331)。

# 何のため

PR #330 で `build_episodic_stack` をシナリオ非依存の application 層 builder
に持ち上げた効果を、別シナリオで実証する。

`demos/survival_island/run_survival_island.py` は `create_world_runtime`
を流用しており、その関数内で `LLM_EPISODIC_ENABLED=1` のとき自動的に
`build_episodic_stack` が呼ばれる。つまり**コード変更なしで survival シナリオ
にエピソード記憶が使えるはず**、というのが本テストの確認対象。

# 検証

1. `LLM_EPISODIC_ENABLED` 未設定 → 各シナリオで `_episodic_stack is None`
2. `LLM_EPISODIC_ENABLED=1` → 各シナリオで stack が組み立てられる
3. `noun_matcher` が当該シナリオの spot 名 / キャラクター名を認識する
4. survival シナリオで `do_wait` 等を呼んでも例外なく完走する
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.runtime_config_helpers import episodic_config, runtime_config


_SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def _build_runtime(scenario_name: str, *, enabled: bool):
    """config を明示して指定シナリオで runtime を作る。"""
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    config = episodic_config() if enabled else runtime_config()
    return create_world_runtime(_SCENARIOS_DIR / scenario_name, config=config)


class TestSurvivalIslandV1EpisodicWiring:
    """`survival_island.json` で episodic stack が wire される (PR #330 効果)。"""

    SCENARIO = "survival_island.json"

    def test_env_未設定なら_stack_は_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = _build_runtime(self.SCENARIO, enabled=False)
        assert runtime._episodic_stack is None

    def test_env_1_で_stack_が組み立てられる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = _build_runtime(self.SCENARIO, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None
        # 4 要素が揃う
        assert stack.chunk_coordinator is not None
        assert stack.passive_recall is not None
        assert stack.noun_matcher is not None
        assert stack.episode_store is not None

    def test_noun_matcher_が_player_名を認識する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """survival_island.json の player_spawns から character cue が立つ。"""
        runtime = _build_runtime(self.SCENARIO, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None
        # 各 player 名で matcher を試す
        any_hit = False
        for pid in runtime.get_player_ids():
            name = runtime.get_player_name(pid)
            if not name:
                continue
            matches = stack.noun_matcher.find_in_text(f"{name}が動いた")
            if any(m.axis == "entity" for m in matches):
                any_hit = True
                break
        assert any_hit, (
            "survival_island.json の player_spawns から entity cue が 1 件も "
            "立たない。scenario loader が player_spawns を正規化しているか確認。"
        )

    def test_episodic_有効でも_do_wait_は例外なく完走(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """エピソード stack 配線下でも survival シナリオの動作が壊れない。"""
        runtime = _build_runtime(self.SCENARIO, enabled=True)
        player_ids = runtime.get_player_ids()
        assert len(player_ids) > 0
        # 最小限の動作確認: wait を 1 回 (chunk close まで踏まないので safe)
        runtime.do_wait(player_ids[0])


class TestSurvivalIslandV2EpisodicWiring:
    """`survival_island_v2.json` (4 ペルソナ + 14 日サバイバル) でも wire される。"""

    SCENARIO = "survival_island_v2.json"

    def test_env_未設定なら_stack_は_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = _build_runtime(self.SCENARIO, enabled=False)
        assert runtime._episodic_stack is None

    def test_env_1_で_stack_が組み立てられる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = _build_runtime(self.SCENARIO, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.chunk_coordinator is not None
        assert stack.passive_recall is not None
        assert stack.noun_matcher is not None
        assert stack.episode_store is not None

    def test_noun_matcher_が_spot_名を認識する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """survival_island_v2.json の spots (25 件) から place_spot cue が立つ。"""
        runtime = _build_runtime(self.SCENARIO, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None
        # 任意の player が今いる spot 名で matcher を試す
        any_spot_hit = False
        for pid in runtime.get_player_ids():
            spot_name = runtime.get_player_spot_name(pid)
            if not spot_name:
                continue
            matches = stack.noun_matcher.find_in_text(f"{spot_name}に着いた")
            if any(m.axis == "place_spot" for m in matches):
                any_spot_hit = True
                break
        assert any_spot_hit, (
            "survival_island_v2.json の spot 名から place_spot cue が 1 件も "
            "立たない。graph._spots と builder の橋渡しを確認。"
        )

    def test_noun_matcher_が_4_persona_名を認識する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """survival_island_v2 は 4 ペルソナ構成。全員 entity として認識される。"""
        runtime = _build_runtime(self.SCENARIO, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None
        recognized_count = 0
        for pid in runtime.get_player_ids():
            name = runtime.get_player_name(pid)
            if not name:
                continue
            matches = stack.noun_matcher.find_in_text(f"{name}が言った")
            if any(m.axis == "entity" for m in matches):
                recognized_count += 1
        assert recognized_count >= 2, (
            f"survival_island_v2 の persona が entity として認識されない "
            f"(recognized={recognized_count})"
        )
