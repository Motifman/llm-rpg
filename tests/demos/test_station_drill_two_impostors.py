"""station_drill の八人構成と、仲間だけに向けた相互開示を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
    GameEndConditionTypeEnum,
)


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_ALLY_MARK = "あなたと同じ側"


def _player_ids(runtime, role: str) -> tuple[PlayerId, ...]:
    return tuple(
        PlayerId(spawn.player_id)
        for spawn in runtime.scenario.player_spawns
        if spawn.initial_state.get("role") == role
    )


def _variant(tmp_path: Path, known_roles: list[str]) -> Path:
    scenario = json.loads(_DRILL.read_text(encoding="utf-8"))
    scenario["mutually_known_roles"] = known_roles
    path = tmp_path / "station_drill_known_roles.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return path


class TestStationDrillHeadcount:
    """参加者はクルー六人・インポスター二人で始まる。"""

    def test_eight_players_have_the_declared_role_split(self) -> None:
        """八人を読み込み、内部 role の内訳が crew 6 / keeper 2 になる。"""
        runtime = create_world_runtime(_DRILL)

        assert len(runtime.get_player_ids()) == 8
        assert len(_player_ids(runtime, "crew")) == 6
        assert len(_player_ids(runtime, "keeper")) == 2

    def test_loss_uses_current_group_comparison_without_a_fixed_threshold(self) -> None:
        """敗北は両陣営の現在人数を比較し、固定の max_surviving を持たない。"""
        runtime = create_world_runtime(_DRILL)
        (condition,) = runtime.scenario.lose_conditions

        assert condition.condition_type is (
            GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE
        )
        assert condition.required_state == {"role": "crew"}
        assert condition.comparison_state == {"role": "keeper"}
        assert condition.max_surviving is None


class TestMutuallyKnownImpostors:
    """仲間の印はインポスター同士だけに現れ、内部 role 名を漏らさない。"""

    def test_each_impostor_system_prompt_marks_the_other(self) -> None:
        """インポスター二人の system には、互いの表示名に仲間の印が付く。"""
        runtime = create_world_runtime(_DRILL)
        keepers = _player_ids(runtime, "keeper")
        names = {
            PlayerId(spawn.player_id): spawn.name
            for spawn in runtime.scenario.player_spawns
        }

        for viewer, ally in ((keepers[0], keepers[1]), (keepers[1], keepers[0])):
            prompt = runtime._world_llm_system_prompts_by_player_id[int(viewer)]
            assert f"- {names[ally]} ({_ALLY_MARK})" in prompt

    def test_no_crew_system_prompt_contains_an_ally_mark(self) -> None:
        """クルー六人には仲間の印を一つも作らず、逆算による役割漏洩を防ぐ。"""
        runtime = create_world_runtime(_DRILL)

        for crew in _player_ids(runtime, "crew"):
            prompt = runtime._world_llm_system_prompts_by_player_id[int(crew)]
            assert _ALLY_MARK not in prompt

    def test_the_mark_does_not_name_the_internal_role(self) -> None:
        """仲間の表示には keeper や管理人という内部・役職語を使わない。"""
        runtime = create_world_runtime(_DRILL)

        for keeper in _player_ids(runtime, "keeper"):
            section = runtime._world_llm_system_prompts_by_player_id[
                int(keeper)
            ].split("【同じ局面にいる者】", 1)[1].split("【渡される文面の内訳】", 1)[0]
            marked = next(line for line in section.splitlines() if _ALLY_MARK in line)
            assert "keeper" not in marked
            assert "管理人" not in marked

    def test_removing_the_declaration_removes_the_positive_mark(
        self, tmp_path: Path
    ) -> None:
        """mutually_known_roles を空にすればインポスターの陽性表示が消える。"""
        runtime = create_world_runtime(_variant(tmp_path, []))

        assert all(
            _ALLY_MARK not in runtime._world_llm_system_prompts_by_player_id[int(pid)]
            for pid in _player_ids(runtime, "keeper")
        )

    def test_declaring_crew_would_mark_crew_and_break_the_negative_contract(
        self, tmp_path: Path
    ) -> None:
        """crew を宣言集合へ足せば印が現れる反例で、陰性試験の有効性を示す。"""
        runtime = create_world_runtime(_variant(tmp_path, ["keeper", "crew"]))

        assert any(
            _ALLY_MARK in runtime._world_llm_system_prompts_by_player_id[int(pid)]
            for pid in _player_ids(runtime, "crew")
        )

    def test_both_impostor_personas_acknowledge_the_known_ally(self) -> None:
        """二人の persona は印と矛盾せず、味方を知らないとは説明しない。"""
        runtime = create_world_runtime(_DRILL)

        for keeper in _player_ids(runtime, "keeper"):
            prompt = runtime._world_llm_system_prompts_by_player_id[int(keeper)]
            assert "あなたは相方が誰かを知っている" in prompt
            assert "他の全員はクルー" not in prompt

    def test_only_kuze_carries_the_control_terminal(self) -> None:
        """端末はクゼだけが持ち、ジンは襲撃と秘密移動を担う。"""
        scenario = json.loads(_DRILL.read_text(encoding="utf-8"))
        holders = [
            player["id"]
            for player in scenario["players"]
            if "control_terminal" in player.get("initial_items", [])
        ]

        assert holders == ["kuze"]

    def test_an_impostor_is_not_offered_an_attack_against_the_known_ally(
        self,
    ) -> None:
        """相方だと表示済みの相手には、必ず拒否される襲撃操作を提示しない。"""
        runtime = create_world_runtime(_DRILL)
        keepers = _player_ids(runtime, "keeper")
        names = {
            PlayerId(spawn.player_id): spawn.name
            for spawn in runtime.scenario.player_spawns
        }

        for viewer, ally in ((keepers[0], keepers[1]), (keepers[1], keepers[0])):
            content = runtime.build_full_prompt(viewer)["messages"][1]["content"]
            ally_line = next(
                line for line in content.splitlines() if f'"{names[ally]}"' in line
            )
            assert "strike_down" not in ally_line


class TestTwoImpostorsCanAttack:
    """二人とも刃物を持ち、同じ手番に別の相手を襲える。"""

    def test_each_impostor_has_a_cutter_and_attacks_a_different_target(self) -> None:
        """同じ ItemSpec を別々に所持し、待ち時間を共有せず二件とも成立する。"""
        runtime = create_world_runtime(_DRILL)
        keepers = _player_ids(runtime, "keeper")
        crew = _player_ids(runtime, "crew")

        for keeper in keepers:
            prompt = runtime.build_full_prompt(keeper)["messages"][1]["content"]
            assert '"解体用カッター"' in prompt

        runtime.do_interact_with_player(keepers[0], crew[0], "strike_down")
        runtime.do_interact_with_player(keepers[1], crew[1], "strike_down")

        assert runtime._player_status_repo.find_by_id(crew[0]).is_down is True
        assert runtime._player_status_repo.find_by_id(crew[1]).is_down is True
        store = runtime._interaction_cooldown_store
        assert store.last_success_tick(keepers[0], "strike_down") == 0
        assert store.last_success_tick(keepers[1], "strike_down") == 0
