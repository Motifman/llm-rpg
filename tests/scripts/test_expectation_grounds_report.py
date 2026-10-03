"""``scripts/expectation_grounds_report.py`` が、清算と受け取る側の trace から、信念とエピソードごとの「頭に載った回数・根拠に選ばれた回数・返った材料の数」を並べることを保証する。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_origin import (
    ExpectationOrigin,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)
from tests.application.being.expectation.support import ScriptedJudgmentPort
from tests.application.being.expectation.test_expectation_grounds_settlement import (
    BELIEFS,
    EPISODES,
    RIO,
    _Harness,
    _recall,
)

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/expectation_grounds_report.py"


@pytest.fixture(scope="module")
def report() -> ModuleType:
    spec = importlib.util.spec_from_file_location("expectation_grounds_report", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trace(harness: _Harness) -> list[dict[str, Any]]:
    return [{"kind": e.kind, "payload": e.payload} for e in harness.recorder.events]


def _row(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    (row,) = [r for r in rows if r["id"] == key]
    return row


def test_counts_in_mind_chosen_and_material_per_belief_and_episode(report: ModuleType) -> None:
    """2 件の予期が同じ信念を頭に載せ、1 件だけが根拠に選んで当たったとき、その信念は頭に 2 回・根拠に 1 回・材料 1 件と並ぶ。"""
    harness = _Harness(
        ScriptedJudgmentPort(
            {"ground_belief_1": 0.9, "ground_episode_1": 0.9},
            {"check_0": "hit", "check_1": "undetermined"},
            {"check_0": "hit", "check_1": "undetermined"},
        )
    )
    harness.form("exp-1")
    harness.repository.save(_second_expectation(harness), [])
    harness.settle_formed_turn()
    harness.turn()
    harness.turn()

    rows = report.rows(report.count(_trace(harness)))

    tom = _row(rows, "belief:belief-tom")
    assert (tom["in_mind"], tom["chosen"], tom["material"]) == (2, 1, 1)
    flat = _row(rows, "belief:belief-flat")
    assert (flat["in_mind"], flat["chosen"], flat["material"]) == (2, 0, 0)
    bread = _row(rows, "episode:ep-bread")
    assert (bread["chosen"], bread["hit_count"], bread["miss_stamp"]) == (1, 1, 0)


def test_miss_stamp_is_counted_for_grounding_episode(report: ModuleType) -> None:
    """根拠のエピソードの想起に外れを書き添えたとき、そのエピソードの外れの書き添えが 1 件と並び、当たりの回数は 0 のまま。"""
    harness = _Harness(
        ScriptedJudgmentPort(
            {"ground_episode_1": 0.9}, {"check_0": "miss"}, {"check_0": "miss"}
        )
    )
    harness.recalls.append_by_being(RIO, _recall("r-bread", "ep-bread"))
    harness.form("exp-1")
    harness.settle_formed_turn()
    harness.turn()
    harness.turn()

    rows = report.rows(report.count(_trace(harness)))

    bread = _row(rows, "episode:ep-bread")
    assert (bread["chosen"], bread["hit_count"], bread["miss_stamp"]) == (1, 0, 1)
    assert bread["material"] is None


def test_unavailable_turn_is_counted_apart_from_in_mind(report: ModuleType) -> None:
    """根拠が決まらなかった予期は頭に載った回数に入れず、縮退の件数として数える。"""
    harness = _Harness(ScriptedJudgmentPort(TypedJudgmentUnavailableException("timeout")))
    harness.form("exp-1")
    harness.settle_formed_turn()

    counts = report.count(_trace(harness))

    assert counts.unjudged == 1
    assert report.rows(counts) == []



def _second_expectation(harness: _Harness) -> Expectation:
    """``harness.form`` と同じターンに、同じものを頭に載せた 2 件目の予期。"""
    turn = harness.repository.current_turn(RIO)
    return Expectation(
        expectation_id=ExpectationId("exp-2"),
        holder=RIO,
        content="干潟でカニに出会う",
        origin=ExpectationOrigin.WITH_ACTION,
        likelihood=Likelihood.PROBABLY,
        formed_at_turn=turn,
        expires_at_turn=turn + 10,
        beliefs_in_mind=tuple(BELIEFS),
        episodes_in_mind=tuple(EPISODES),
    )
