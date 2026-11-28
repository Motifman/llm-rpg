from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.fuzz_scenario_with_random_agents import (  # noqa: E402
    game_world_identifiers,
    main,
    run_random_agents_in_game_world,
)

from ai_rpg_world.being.application.choose_action import ActionChoosingReply  # noqa: E402
from ai_rpg_world.being.domain.working_memory import Closing  # noqa: E402
from ai_rpg_world.experiment.infrastructure import game_world_run, random_action_choosing  # noqa: E402

_MINE_VILLAGE_V2 = _REPO_ROOT / "data" / "scenarios" / "mine_village_v2.yaml"
_PROFILE = _REPO_ROOT / "data" / "experiment_profiles" / "smoke_stub_game_world.json"


def _fuzz(seed: int = 0, ticks: int = 3) -> Any:
    return run_random_agents_in_game_world(_MINE_VILLAGE_V2, seed=seed, max_world_ticks=ticks, profile_path=_PROFILE)


class TestFuzzInTheGameWorld:
    """fuzz が、新しい世界の profile のとき、でたらめなスタブで廃坑の山村 v2 を回し、例外と漏れを見つけることを保証する。"""

    def test_same_seed_gives_the_same_actions(self) -> None:
        """同じシードで 2 回回すと、行動の並びが同じになる。"""
        first, second = _fuzz(seed=3), _fuzz(seed=3)

        assert [a.describe() for a in first.actions] == [a.describe() for a in second.actions]
        assert first.actions

    def test_clean_run_reaches_the_round_limit_without_findings(self) -> None:
        """シード 0 で 3 巡り回すと、3 tick まで進み、見つけたものは無い。"""
        result = _fuzz()

        assert (result.reached_tick, result.findings) == (3, [])

    def test_scenario_identifier_in_the_prompt_is_found_as_a_leak(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """締めの文にシナリオの ID (lift_key) が混ざると、その行を leak として見つける。"""
        monkeypatch.setattr(game_world_run, "CLOSING", Closing(instruction="lift_key を取りに行ってください。"))

        result = _fuzz(ticks=1)

        assert [f.kind for f in result.findings] == ["leak"]
        assert "lift_key" in result.findings[0].detail

    def test_choosing_that_raised_is_found_as_a_swallowed_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """行動を選ぶ途中で例外が出て、選べなかったターンとして飲まれると、swallowed_exception として見つける。"""

        def broken(*_: Any, **__: Any) -> ActionChoosingReply:
            raise KeyError("candidate table changed shape")

        monkeypatch.setattr(random_action_choosing, "choose_random_call", broken)

        result = _fuzz(ticks=1)

        assert {f.kind for f in result.findings} == {"swallowed_exception"}
        assert "candidate table changed shape" in result.findings[0].detail

    def test_identifiers_come_from_the_nouns_and_the_item_specs(self) -> None:
        """廃坑の山村 v2 の識別子に、場所 (north_shaft_head) と品物 (lift_key) が入り、下線の無い名前は入らない。"""
        identifiers = game_world_identifiers(_MINE_VILLAGE_V2)

        assert {"north_shaft_head", "lift_key"} <= identifiers
        assert all("_" in i for i in identifiers)

    def test_main_uses_the_game_world_when_the_profile_says_so(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--profile に新しい世界の profile を渡すと、新しい世界で回し、0 で終わる。"""
        code = main(["--scenario", str(_MINE_VILLAGE_V2), "--seeds", "0", "--ticks", "1", "--profile", str(_PROFILE)])

        assert code == 0
        assert "OK   mine_village_v2 seed=0 ticks=1 reached=1" in capsys.readouterr().out
