"""死亡・追放を含む world snapshot が公開の問いを同じ意味で復元する。"""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copy2

import pytest

from ai_rpg_world.application.being.experiment_snapshot_session import (
    ExperimentSnapshotSession,
)
from ai_rpg_world.application.being.world_state_snapshot import (
    WorldStateSnapshotVersionError,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.demos._world_runtime_helpers import create_world_runtime_session


_SENA = PlayerId(2)
_KUZE = PlayerId(3)


def _build_runtime_and_snapshot_session(
    root: Path, monkeypatch: pytest.MonkeyPatch
):
    state = create_world_runtime_session(
        monkeypatch,
        root,
        world_id="station_drill",
    )
    runtime = state.runtime
    runtime._wire_auxiliary_tool_stack()
    for player_id in runtime.get_player_ids():
        runtime._aux_being_provisioning.ensure_attached(player_id)

    from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

    session = ExperimentSnapshotSession(
        wiring_result=_wiring_stub_from_world_runtime(runtime),
        snapshot_dir=root / "snapshots",
    )
    return state, session


def _capture(session: ExperimentSnapshotSession, runtime) -> Path:
    return session.capture_world(
        runtime,
        source_scenario="station_drill",
        world_tick=int(runtime.current_tick()),
    )


class TestPlayerOutcomeSnapshotSemantics:
    """復元前後で勝敗・投票資格・手番可否の答えが一致する。"""

    def test_dead_and_ejected_players_keep_the_same_public_meaning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DEAD と EJECTED が復元後に生存者や投票者へ戻らない。"""
        source_state, source_session = _build_runtime_and_snapshot_session(
            tmp_path / "source", monkeypatch
        )
        source = source_state.runtime
        sena = source._player_status_repo.find_by_id(_SENA)
        sena.apply_damage(sena.hp.value)
        source._player_status_repo.save(sena)
        source._player_outcome_registry.set_outcome(_SENA, PlayerOutcomeEnum.DEAD)
        assert source.eject_player(_KUZE) is True

        expected_game_end = source.check_game_end()
        expected_voters = source.eligible_voters()
        expected_can_act = {
            player_id: source_state.llm_wiring.llm_turn_trigger._can_player_act(
                int(player_id)
            )
            for player_id in (_SENA, _KUZE)
        }
        snapshot_path = _capture(source_session, source)

        restored_state, restored_session = _build_runtime_and_snapshot_session(
            tmp_path / "restored", monkeypatch
        )
        restored_dir = tmp_path / "restored" / "snapshots"
        restored_dir.mkdir(parents=True, exist_ok=True)
        copy2(snapshot_path, restored_dir / "world.json")
        restored_session.restore_world_from_dir(
            restored_state.runtime,
            restored_dir,
            current_scenario="station_drill",
        )

        restored = restored_state.runtime
        assert restored.check_game_end() == expected_game_end
        assert restored.eligible_voters() == expected_voters
        assert {
            player_id: restored_state.llm_wiring.llm_turn_trigger._can_player_act(
                int(player_id)
            )
            for player_id in (_SENA, _KUZE)
        } == expected_can_act
        assert restored._player_outcome_registry.get_outcome(_SENA) is (
            PlayerOutcomeEnum.DEAD
        )
        assert restored._player_outcome_registry.get_outcome(_KUZE) is (
            PlayerOutcomeEnum.EJECTED
        )

    def test_version_two_is_rejected_before_restoring_an_incomplete_world(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """outcome の無い版 2 は公開 resume 入口で理由を示して拒否する。"""
        source_state, source_session = _build_runtime_and_snapshot_session(
            tmp_path / "source", monkeypatch
        )
        snapshot_path = _capture(source_session, source_state.runtime)
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        data["schema_version"] = 2
        data["subsystems"].pop("player_outcome")

        restored_state, restored_session = _build_runtime_and_snapshot_session(
            tmp_path / "restored", monkeypatch
        )
        restored_dir = tmp_path / "restored" / "snapshots"
        restored_dir.mkdir(parents=True, exist_ok=True)
        (restored_dir / "world.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        with pytest.raises(
            WorldStateSnapshotVersionError,
            match="死亡・追放の確定.*勝敗",
        ):
            restored_session.restore_world_from_dir(
                restored_state.runtime,
                restored_dir,
                current_scenario="station_drill",
            )
