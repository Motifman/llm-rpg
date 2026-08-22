"""player outcome ruleのrule単位確定境界を保証する。"""

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from tests.runtime_config_helpers import runtime_config


_SOURCE = Path("data/scenarios/survival_island_v2_short.json")


def _scenario(
    tmp_path: Path,
    *,
    rules: list[dict[str, Any]] | None = None,
) -> Path:
    raw = json.loads(_SOURCE.read_text(encoding="utf-8"))
    raw["player_outcome_rules"] = rules or [
        {
            "id": "rescue_everyone",
            "trigger": {
                "condition_type": "PROBABILITY",
                "probability": 1.0,
            },
            "once": True,
            "player_conditions": [],
            "outcome": "RESCUED",
        }
    ]
    path = tmp_path / "player_outcome_rule_scope.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _runtime(tmp_path: Path, *, rules: list[dict[str, Any]] | None = None) -> Any:
    return create_world_runtime(
        _scenario(tmp_path, rules=rules),
        config=runtime_config(scenario_random_seed=42),
    )


def _stage(runtime: Any) -> Any:
    return runtime._simulation_service._player_outcome_rule_stage


def _outcomes(runtime: Any) -> dict[int, PlayerOutcomeEnum]:
    return runtime._player_outcome_registry.snapshot()


def test_progress_failure_rolls_back_all_outcomes_and_probability_rng(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全員確定後の進捗失敗では、outcome・進捗・確率乱数を開始前へ戻す。"""
    runtime = _runtime(tmp_path)
    progress = runtime._scenario_event_progress
    evaluator = _stage(runtime)._condition_evaluator
    before_rng = evaluator.rollback_snapshot()
    observed: list[int] = []
    runtime._player_outcome_registry.register_callback(
        lambda player_id, _old, _new: observed.append(int(player_id))
    )
    original_mark_fired = progress.mark_fired

    def mark_then_fail(progress_id: str) -> None:
        original_mark_fired(progress_id)
        raise RuntimeError("progress save failed")

    monkeypatch.setattr(progress, "mark_fired", mark_then_fail)

    with pytest.raises(RuntimeError, match="progress save failed"):
        _stage(runtime).run(WorldTick(1))

    assert set(_outcomes(runtime).values()) == {PlayerOutcomeEnum.UNRESOLVED}
    assert not progress.is_fired("player_outcome_rule:rescue_everyone")
    assert evaluator.rollback_snapshot() == before_rng
    assert observed == []


def test_success_observes_all_outcomes_and_progress_after_commit(
    tmp_path: Path,
) -> None:
    """各callbackは全員のoutcomeと一度限り進捗が確定した後だけ呼ばれる。"""
    runtime = _runtime(tmp_path)
    progress_id = "player_outcome_rule:rescue_everyone"
    observations: list[tuple[int, bool, frozenset[PlayerOutcomeEnum]]] = []

    def observe(player_id: Any, _old: Any, _new: Any) -> None:
        observations.append(
            (
                int(player_id),
                runtime._scenario_event_progress.is_fired(progress_id),
                frozenset(_outcomes(runtime).values()),
            )
        )

    runtime._player_outcome_registry.register_callback(observe)

    _stage(runtime).run(WorldTick(1))

    assert [entry[0] for entry in observations] == [
        int(player_id) for player_id in runtime.get_player_ids()
    ]
    assert all(entry[1] is True for entry in observations)
    assert all(
        entry[2] == frozenset({PlayerOutcomeEnum.RESCUED})
        for entry in observations
    )


def test_post_commit_cleanup_failure_notifies_then_preserves_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit済みcleanup失敗では確定outcomeを通知して専用例外を維持する。"""
    runtime = _runtime(tmp_path)
    observed: list[int] = []
    runtime._player_outcome_registry.register_callback(
        lambda player_id, _old, _new: observed.append(int(player_id))
    )
    data_store = runtime._item_repo._data_store
    original_release = data_store.release_uow_transaction

    def release_then_fail() -> None:
        original_release()
        raise RuntimeError("outcome cleanup failed")

    monkeypatch.setattr(data_store, "release_uow_transaction", release_then_fail)

    with pytest.raises(CommandPostCommitException):
        _stage(runtime).run(WorldTick(1))

    assert set(_outcomes(runtime).values()) == {PlayerOutcomeEnum.RESCUED}
    assert runtime._scenario_event_progress.is_fired(
        "player_outcome_rule:rescue_everyone"
    )
    assert observed == [int(player_id) for player_id in runtime.get_player_ids()]


def test_committed_rule_survives_later_rule_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """先行ruleの確定は、後続ruleの進捗失敗で巻き戻されない。"""
    rules = [
        {
            "id": "first_rescue",
            "trigger": {"condition_type": "TICK_AT_LEAST", "tick": 1},
            "once": True,
            "player_conditions": [],
            "outcome": "RESCUED",
        },
        {
            "id": "later_opportunity",
            "trigger": {"condition_type": "TICK_AT_LEAST", "tick": 1},
            "once": True,
            "player_conditions": [],
            "outcome": "STRANDED",
        },
    ]
    runtime = _runtime(tmp_path, rules=rules)
    progress = runtime._scenario_event_progress
    original_mark_fired = progress.mark_fired

    def fail_later(progress_id: str) -> None:
        original_mark_fired(progress_id)
        if progress_id.endswith("later_opportunity"):
            raise RuntimeError("later rule failed")

    monkeypatch.setattr(progress, "mark_fired", fail_later)

    with pytest.raises(RuntimeError, match="later rule failed"):
        _stage(runtime).run(WorldTick(1))

    assert set(_outcomes(runtime).values()) == {PlayerOutcomeEnum.RESCUED}
    assert progress.is_fired("player_outcome_rule:first_rescue")
    assert not progress.is_fired("player_outcome_rule:later_opportunity")


def test_runtime_wires_outcome_progress_and_rng_as_participants(
    tmp_path: Path,
) -> None:
    """本番factoryはoutcome・進捗・条件乱数の共有instanceを参加させる。"""
    runtime = _runtime(tmp_path)
    stage = _stage(runtime)
    factory = stage._command_scope_factory
    transaction_factory = factory._transaction_factory
    resources = {
        participant.rollback_resource
        for participant in transaction_factory._participants
    }

    assert runtime._player_outcome_registry in resources
    assert runtime._scenario_event_progress in resources
    assert stage._condition_evaluator in resources


def test_waiting_once_command_rechecks_progress_inside_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同時実行がscope前確認を共に通っても、triggerは一度だけ評価する。"""
    runtime = _runtime(tmp_path)
    stage = _stage(runtime)
    progress = runtime._scenario_event_progress
    original_is_fired = progress.is_fired
    outside_checks = threading.Barrier(2)
    check_lock = threading.Lock()
    check_count = 0
    trigger_lock = threading.Lock()
    trigger_count = 0
    errors: list[BaseException] = []

    def synchronized_is_fired(progress_id: str) -> bool:
        nonlocal check_count
        with check_lock:
            check_count += 1
            current_check = check_count
        if current_check <= 2:
            outside_checks.wait(timeout=5)
        return original_is_fired(progress_id)

    original_evaluate = stage._condition_evaluator.evaluate_diagnostic

    def count_trigger(*args: Any, **kwargs: Any) -> Any:
        nonlocal trigger_count
        with trigger_lock:
            trigger_count += 1
        return original_evaluate(*args, **kwargs)

    monkeypatch.setattr(progress, "is_fired", synchronized_is_fired)
    monkeypatch.setattr(
        stage._condition_evaluator,
        "evaluate_diagnostic",
        count_trigger,
    )

    def run_stage() -> None:
        try:
            stage.run(WorldTick(1))
        except BaseException as exc:  # pragma: no cover - assertion below
            errors.append(exc)

    threads = [threading.Thread(target=run_stage) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert trigger_count == 1
    assert progress.is_fired("player_outcome_rule:rescue_everyone")
