"""廃坑の山村で、発言を変えながら同じ金庫を試し続けると、ループ警告が出ることを保証する (#1594)。

`var/runs/mine_v1_005` では、ハルが同じ金庫を同じ番号で 4 回試してもループ警告が
0 件だった。発言 (`say_inline`) が毎回違い、1 回目は対象名を引用符つきで渡して
いたので、同じ行動として数えられなかった。

dispatch は引数に解決済みの識別値などの内部キーを足してから loop guard に渡す。
loop guard を直接呼ぶ試験ではこの経路を通らないので、本番と同じ session を組み、
プロンプトの対象表を使って `run_phase_b` から試す。
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"
_HAL = PlayerId(1)
#: ハルが mine_v1_005 の T20、T24、T30 に送った引数の形。離れた tick の同じ失敗の閾値は 3 回。
_ATTEMPTS = (
    ('"金庫"', "ミオ、机に「金庫 1907」と書いた紙切れがあった。この番号で合わせてみる。"),
    ("金庫", "ミオ、机の紙にあった番号を入れてみる。番号の渡し方を変えて試す。"),
    ("金庫", "ミオ、番号を明示して合わせてみる。1907だ。"),
)


@pytest.fixture(autouse=True)
def _without_developer_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class _Trace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):  # type: ignore[no-untyped-def]
        self.events.append({"kind": kind, "player_id": player_id, **payload})


def _session_with_hal_in_the_office(tmp: str):
    manager = GameRuntimeManager(
        scenarios_dir=_SCENARIO.parent,
        characters_path=Path(tmp) / "characters.json",
        runtime_config=ResolvedLlmRuntimeConfig.for_tests(
            typed_judgment_provider="stub",
            typed_judgment_loop_diagnosis_enabled=True,
        ),
    )
    character = manager.create_character(CharacterCreateRequest(name="probe"))
    summary = manager.create_session(
        SessionCreateRequest(world_id=_SCENARIO.stem, character_ids=[character.id])
    )
    wiring = manager._sessions[summary.session_id].llm_wiring
    runtime = wiring.runtime
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(_HAL))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", "company_office")))
    runtime._spot_graph_repo.save(graph)
    return wiring


def _act(wiring, tool_name: str, arguments: dict[str, Any]):
    return wiring.run_phase_b(
        LlmPhaseAResult(
            player_id=_HAL,
            prompt=wiring.runtime.build_full_prompt(_HAL),
            tools_payload=[],
            tool_call={"name": tool_name, "arguments": arguments},
            exception=None,
        )
    )


def _try_the_safe(wiring, target_label: str, said: str):
    return _act(
        wiring,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        {
            "target_label": target_label,
            "action_name": "open_safe",
            "parameters": {"text": "1907"},
            "say_inline": said,
            "inner_thought": "番号は合っているはずだ。",
        },
    )


def _search_the_office(wiring):
    return _act(
        wiring,
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        {"say_inline": "帳簿棚を洗ってみる。", "inner_thought": "手がかりが要る。"},
    )


class TestSafeRetriedWithNewWords:
    """発言と対象名の書き方を変えても、同じ金庫を同じ番号で試す行動を同じ行動として数えることを保証する。"""

    def test_retrying_the_safe_with_new_words_raises_a_warning_and_asks_why(self) -> None:
        """発言を毎回変え、1 回目だけ対象名を引用符つきにし、間に探索を挟んで金庫を 3 回試すと、同じ失敗の繰り返しとしてループ警告が 1 件出て、繰り返しの理由を問う判断が 1 回呼ばれる。"""
        with TemporaryDirectory() as tmp:
            wiring = _session_with_hal_in_the_office(tmp)
            trace = _Trace()
            wiring.runtime.set_trace_recorder(trace)

            results = []
            for target, said in _ATTEMPTS:
                results.append(_try_the_safe(wiring, target, said))
                _search_the_office(wiring)

            warnings = [
                e for e in trace.events
                if e["kind"] == TraceEventKind.LOOP_GUARD_WARNING and e["player_id"] == int(_HAL)
            ]
            diagnoses = [
                e for e in trace.events
                if e["kind"] == TraceEventKind.TYPED_JUDGMENT
                and e.get("question") == "loop_diagnosis"
            ]
            assert [r.success for r in results] == [False] * len(_ATTEMPTS)
            assert [w.get("pattern") for w in warnings] == ["cross_tick_failure"], warnings
            assert len(diagnoses) == 1, diagnoses
