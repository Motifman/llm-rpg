"""Encounter Memory 〜 prompt 露出の E2E 統合テスト (PR4)。

実 ``WorldRuntime`` を立てて ``build_full_prompt`` 経由で:

- 初訪問 spot に対して「現在地: 〇〇 (初めて訪れた)」が出る
- 同 spot にいる他 player に対して「- 名前 (初めて会った)」が出る
- 同 spot に他 player がいない場合は player familiarity 注記は出ない

run の起動コストが高いため、scenario は固定 (forbidden_library_demo)。
"""

from __future__ import annotations

import re
from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _create_runtime():
    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    return create_world_runtime(_SCENARIO_PATH)


def _user_prompt_text(runtime, player_id) -> str:
    prompt = runtime.build_full_prompt(player_id)
    # messages[0] = system, messages[1] = user
    return prompt["messages"][1]["content"]


def _current_state_section(text: str) -> str:
    """``【現在地と周囲】`` セクションを抽出する。"""
    m = re.search(r"【現在地と周囲】.*?(?=\n【|\Z)", text, re.DOTALL)
    return m.group(0) if m else ""


class TestCurrentSpotFamiliarityE2E:
    """初回 spawn 直後の player について「初めて訪れた」が prompt に出る。"""

    def test_spawn_after_player_current_spot_rendered(self) -> None:
        """spawn 直後の player は現在地に初めて訪れたが出る。"""
        runtime = _create_runtime()
        kaito = runtime.get_player_ids()[0]
        section = _current_state_section(_user_prompt_text(runtime, kaito))
        # kaito の spawn spot は entrance_hall = 入口広間
        assert "現在地: 入口広間 (初めて訪れた)" in section, section

    def test_different_player_independently_rendered(self) -> None:
        """別 player も独立に初めて訪れたが出る。"""
        runtime = _create_runtime()
        rin = runtime.get_player_ids()[1]
        section = _current_state_section(_user_prompt_text(runtime, rin))
        # rin の spawn spot は reading_room = 閲覧室
        assert "現在地: 閲覧室 (初めて訪れた)" in section, section


class TestNearbyPlayerFamiliarityE2E:
    """別々の場所から始めた二人が顔を合わせると、双方の【現在地と周囲】で相手に「初めて会った」が付く。"""

    def test_both_sides_see_first_meeting_after_one_walks_in(self) -> None:
        """カイトがリンのいる閲覧室へ歩いて入ると、入った側のカイトにも、いた側のリンにも、相手の名前に (初めて会った) が付く。"""
        runtime = _create_runtime()
        kaito, rin = runtime.get_player_ids()[:2]

        runtime.do_move(kaito, "reading_room")
        runtime.advance_until_player_idle(kaito)

        rin_section = _current_state_section(_user_prompt_text(runtime, rin))
        kaito_section = _current_state_section(_user_prompt_text(runtime, kaito))
        assert '"カイト" (初めて会った)' in rin_section, rin_section
        assert '"リン" (初めて会った)' in kaito_section, kaito_section


class TestPromptRegressionForViewer:
    """encounter wiring が prompt 構造を壊さないことを確認する regression test。"""

    def test_prompt_section_included(self) -> None:
        """prompt に必須 section がすべて含まれる。"""
        runtime = _create_runtime()
        kaito = runtime.get_player_ids()[0]
        text = _user_prompt_text(runtime, kaito)
        assert "【現在の目的】" in text
        assert "【現在地と周囲】" in text
        # 注記は最低 1 つは出る (spawn spot は確実に「初訪問」)
        assert "(初めて訪れた)" in text

    def test_messages_two_system_user(self) -> None:
        """messages は 2 件 system user。"""
        runtime = _create_runtime()
        kaito = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(kaito)
        assert len(prompt["messages"]) == 2
        assert prompt["messages"][0]["role"] == "system"
        assert prompt["messages"][1]["role"] == "user"


class _TraceRecorderSpy:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):  # noqa: ANN001
        self.events.append((str(kind), {"tick": tick, "player_id": player_id, **payload}))

    def close(self) -> None:
        pass


class TestEncounterCuesReachEpisodicRecall:
    """Issue #1445: episodic 記憶を有効にした runtime で、遭遇の記録が受動想起の situation_cues まで届く。"""

    def _situation_cues_by_recall(self, trace_kinds) -> dict[str, list[str]]:  # noqa: ANN001
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )
        from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
            EncounterKey,
        )
        from tests.runtime_config_helpers import episodic_config

        runtime = create_world_runtime(
            _SCENARIO_PATH, config=episodic_config(semantic_passive_top_k=3)
        )
        rin = runtime.get_player_ids()[1]
        tick = runtime.current_tick()
        runtime._player_acquaintances.record_meeting(rin, "カイト")
        runtime._encounter_memory.observe(rin, EncounterKey.spot("entrance_hall"), tick)
        self.entrance_hall = runtime.id_mapper.get_int("spot", "entrance_hall")
        recorder = _TraceRecorderSpy()
        runtime.set_trace_recorder(recorder)

        runtime.build_full_prompt(rin)

        cues: dict[str, list[str]] = {}
        for kind, payload in recorder.events:
            if kind in trace_kinds:
                cues[kind] = list(payload["situation_cues"])
        assert set(cues) == set(trace_kinds), f"trace が出ていない: {set(trace_kinds) - set(cues)}"
        return cues

    def test_met_player_and_visited_spot_become_situation_cues(self) -> None:
        """知り合いの記録で直近に会った 'カイト' と、環境の encounter でいま居ない場所 entrance_hall に遭遇した記録から、episodic と semantic の両方の受動想起の situation_cues に entity:actor_カイト と entrance_hall の数値 ID の place_spot cue が入る。"""
        from ai_rpg_world.application.trace.events import TraceEventKind

        kinds = (TraceEventKind.EPISODIC_RECALL, TraceEventKind.SEMANTIC_PASSIVE_RECALL)

        cues = self._situation_cues_by_recall(kinds)

        for kind in kinds:
            assert "entity:actor_カイト" in cues[kind], kind
            assert f"place_spot:{self.entrance_hall}" in cues[kind], kind
