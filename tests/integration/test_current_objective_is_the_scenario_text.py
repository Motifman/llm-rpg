"""【現在の目的】が、シナリオに書いた目的の文とバイト単位で同じであることを保証する。

目的の文は、プレイヤーの ``objective`` があればそれ、無ければ
``metadata.llm_objective_text``。どちらも前後の空白を除いて、見出しの直後に
そのまま載る。シナリオの JSON から直接読んだ文と比べるので、途中の解決の経路が
変わっても、文面が 1 文字でも変われば落ちる。LLM は呼ばない。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import runtime_config

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_SCENARIO_FILES = sorted(
    path.name for path in _SCENARIOS.glob("*.json") if "players" in json.loads(path.read_text(encoding="utf-8"))
)


def _written_objectives(scenario_file: str) -> dict[str, str]:
    raw = json.loads((_SCENARIOS / scenario_file).read_text(encoding="utf-8"))
    common = (raw.get("metadata") or {}).get("llm_objective_text") or ""
    return {player["id"]: (player.get("objective") or common).strip() for player in raw["players"]}


def _user_content(runtime, player_id: PlayerId) -> str:
    return runtime.build_full_prompt(player_id)["messages"][1]["content"]


def test_every_scenario_is_checked() -> None:
    """正の対照: 対象のシナリオを 1 本も拾えていないと、下の検査が空振りする。"""
    assert len(_SCENARIO_FILES) >= 19


@pytest.mark.parametrize("scenario_file", _SCENARIO_FILES)
def test_current_objective_is_the_text_written_in_the_scenario(scenario_file: str) -> None:
    """各プレイヤーの【現在の目的】の直後に、シナリオに書いた目的の文がそのまま載る。"""
    runtime = create_world_runtime(_SCENARIOS / scenario_file, config=runtime_config())
    written = _written_objectives(scenario_file)
    string_ids = {spawn.player_id: spawn.string_id for spawn in runtime.scenario.player_spawns}

    for player_id in runtime.get_player_ids():
        expected = written[string_ids[player_id.value]]

        user = _user_content(runtime, player_id)

        assert f"【現在の目的】\n{expected}\n\n" in user, f"{scenario_file} {string_ids[player_id.value]}"
