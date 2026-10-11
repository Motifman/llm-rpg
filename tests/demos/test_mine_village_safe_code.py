"""廃坑の山村 (`mine_village_v1`) の金庫が、プロンプトに出た表示だけを頼りに開けられることを保証する。

`var/runs/mine_v1_005` では、金庫の行に番号を渡すキーが出ておらず、4 人とも
`{"text": "1907"}` で呼んで失敗した。返った文は番号違いと同じで、全員が番号を
疑って坑道へ戻った (Issue #1591)。

試験にキーを直書きすると、表示の抜けを見逃す。だからここではプロンプトの金庫の
行からキーを読み取り、それで引数を組む。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_GEN = PlayerId(3)
_SAFE_CODE = "1907"
_WRONG_NUMBER_TEXT = "ダイヤルを合わせて把手を引いたが、扉はびくともしない。"
_REQUIRED_KEY = re.compile(r'"([^"]+)" が要る')


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_SCENARIO)
    graph = rt._spot_graph_repo.find_graph()
    entity = EntityId.create(int(_GEN))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(rt.id_mapper.get_int("spot", "company_office")))
    rt._spot_graph_repo.save(graph)
    return rt


def _safe_row(runtime) -> str:
    prompt = runtime.build_full_prompt(_GEN)
    body = "\n".join(str(m.get("content", "")) for m in prompt["messages"])
    rows = [line for line in body.splitlines() if '"open_safe"' in line]
    assert len(rows) == 1, rows
    return rows[0]


def _try_open(runtime, parameters: dict[str, str]) -> tuple[str, str]:
    try:
        result = runtime.do_interact(
            _GEN, "office_safe", "open_safe", interaction_parameters=parameters
        )
    except InteractionNotAllowedException as exc:
        return "refused", str(exc)
    return "done", "\n".join(result.messages)


class TestSafeRowShowsTheKeyToEnterTheNumber:
    """金庫の行に出た「が要る」のキーで番号を渡せば開き、キーが違えば番号違いと区別できる文が返ることを保証する。"""

    def test_the_key_read_from_the_safe_row_opens_the_safe_with_the_right_number(self, runtime) -> None:
        """事務所にいる人のプロンプトの金庫の行から「"…" が要る」のキーを 1 つ読み取り、そのキーで 1907 を渡すと金庫が開く。"""
        keys = _REQUIRED_KEY.findall(_safe_row(runtime))

        outcome, text = _try_open(runtime, {key: _SAFE_CODE for key in keys})

        assert len(keys) == 1, keys
        assert (outcome, "金庫の扉が開いた" in text) == ("done", True), text

    def test_calling_without_the_shown_key_names_the_key_instead_of_saying_the_number_was_wrong(
        self, runtime
    ) -> None:
        """表示されたキーを使わず `{"text": "1907"}` で呼ぶと断られ、返る文は表示されたキーを名指し、番号違いの文ではない。"""
        (key,) = _REQUIRED_KEY.findall(_safe_row(runtime))

        outcome, text = _try_open(runtime, {"text": _SAFE_CODE})

        assert outcome == "refused"
        assert f'"{key}"' in text, text
        assert _WRONG_NUMBER_TEXT not in text

    def test_a_wrong_number_under_the_shown_key_keeps_the_scenario_wording(self, runtime) -> None:
        """表示されたキーで違う番号を渡すと断られ、シナリオが書いた番号違いの文が返る。"""
        (key,) = _REQUIRED_KEY.findall(_safe_row(runtime))

        outcome, text = _try_open(runtime, {key: "0000"})

        assert (outcome, text) == ("refused", _WRONG_NUMBER_TEXT)
