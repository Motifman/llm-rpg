"""PR8 (R5): Encounter event を recall trigger に乗せる経路の検証。

R5 の狙い:
- 直近 N tick 以内に encounter (初対面 / 再会) した entity / spot / event を
  ``EpisodicCueSource.ENCOUNTER`` の cue として ``situation_cues`` に乗せる
- 構造化 spawn / arrival 観測しか無い場面でも、過去 episode が recall される
  ようになる
"""

from __future__ import annotations

from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    _cues_from_recent_encounters,
    build_situation_episodic_cues,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

PID = PlayerId(7)


class TestR5RecentEncounterCues:
    """R5: ``_cues_from_recent_encounters`` の挙動。"""

    def test_player_kind_maps_to_entity_axis(self) -> None:
        """kind=player の表示名 'Alice' は、axis=entity, value='actor_alice' の ENCOUNTER cue になる。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("Alice"), current_tick=10)
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=10,
            recent_window_ticks=5,
        )
        assert len(cues) == 1
        assert cues[0].axis == "entity"
        assert cues[0].value == "actor_alice"
        assert cues[0].source == EpisodicCueSource.ENCOUNTER

    def test_spot_kind_maps_to_place_spot_axis(self) -> None:
        """kind=spot → axis=place_spot, value={id}。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.spot("7"), current_tick=20)
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=20,
            recent_window_ticks=5,
        )
        assert len(cues) == 1
        assert cues[0].axis == "place_spot"
        assert cues[0].value == "7"
        assert cues[0].source == EpisodicCueSource.ENCOUNTER

    def test_event_kind_maps_to_action_axis(self) -> None:
        """kind=event → axis=action, value={sanitized event-type}。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.event("storm_arrived"), current_tick=30)
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=30,
            recent_window_ticks=5,
        )
        assert len(cues) == 1
        assert cues[0].axis == "action"
        assert cues[0].value == "storm_arrived"
        assert cues[0].source == EpisodicCueSource.ENCOUNTER

    def test_outside_recent_window_skipped(self) -> None:
        """``last_seen_tick`` が window より古い encounter は cue 化しない。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("42"), current_tick=10)
        # current_tick=20 で window=5 → delta=10 → 範囲外
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=20,
            recent_window_ticks=5,
        )
        assert cues == []

    def test_zero_delta_included(self) -> None:
        """``current_tick == last_seen_tick`` (delta=0) は即座に cue 化される。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("42"), current_tick=20)
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=20,
            recent_window_ticks=5,
        )
        assert len(cues) == 1

    def test_inside_recent_window_included(self) -> None:
        """``last_seen_tick`` が window 内なら cue 化される (境界条件: delta == window)。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("42"), current_tick=15)
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=20,
            recent_window_ticks=5,
        )
        assert len(cues) == 1

    def test_re_encounter_also_emits_cue(self) -> None:
        """再会 (count > 1) でも同じ cue が立つ。is_first で挙動を変えない。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.spot("7"), current_tick=10)
        mem.observe(PID, EncounterKey.spot("7"), current_tick=20)  # 再会
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=20,
            recent_window_ticks=5,
        )
        assert len(cues) == 1
        assert cues[0].axis == "place_spot"
        assert cues[0].value == "7"

    def test_future_tick_skipped(self) -> None:
        """``current_tick - last_seen_tick < 0`` (= 記録 tick の方が未来) は skip。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("42"), current_tick=30)
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=20,
            recent_window_ticks=5,
        )
        assert cues == []

    def test_no_records_for_player_returns_empty(self) -> None:
        """encounter memory に該当 player の record が無いなら空 list。"""
        mem = InMemoryEncounterMemory()
        cues = _cues_from_recent_encounters(
            encounter_memory=mem,
            player_id=PID,
            current_tick=10,
            recent_window_ticks=5,
        )
        assert cues == []

    def test_encounter_memory_exception_returns_empty(self) -> None:
        """encounter memory が例外を出しても recall を止めず空 list で fallback。"""

        class BrokenMemory:
            def get_records_for(self, _player_id):  # type: ignore[no-untyped-def]
                raise RuntimeError("boom")

        cues = _cues_from_recent_encounters(
            encounter_memory=BrokenMemory(),  # type: ignore[arg-type]
            player_id=PID,
            current_tick=10,
            recent_window_ticks=5,
        )
        assert cues == []


class TestR5IntegrationViaBuildSituationCues:
    """R5: ``build_situation_episodic_cues`` から呼んだときの統合挙動。"""

    def test_encounter_cue_appears_in_situation_cues(self) -> None:
        """encounter_memory + player_id + current_tick が揃えば cue が出る。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("alice"), current_tick=10)
        cues = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            encounter_memory=mem,
            encounter_player_id=PID,
            encounter_current_tick=10,
            encounter_recent_window_ticks=5,
        )
        canonicals = {c.to_canonical() for c in cues}
        assert "entity:actor_alice" in canonicals

    def test_missing_encounter_args_is_noop(self) -> None:
        """encounter_memory / player_id / current_tick のどれかが None なら cue 出ない。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("42"), current_tick=10)
        # current_tick=None
        cues = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            encounter_memory=mem,
            encounter_player_id=PID,
            encounter_current_tick=None,
        )
        assert cues == ()
        # encounter_memory=None
        cues2 = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            encounter_memory=None,
            encounter_player_id=PID,
            encounter_current_tick=10,
        )
        assert cues2 == ()

    def test_encounter_cue_dedupes_with_runtime_cue(self) -> None:
        """encounter 由来と runtime 由来が同 (axis, value) なら 1 件にまとまる。

        ただし source は ``_validate_and_dedupe`` の挙動で **最初に来た方**
        が勝つ。挿入順は runtime → encounter なので runtime source が残る。
        """
        from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto

        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.spot("7"), current_tick=10)
        rt = ToolRuntimeContextDto(
            current_spot_id=7,
            current_sub_location_id=None,
            current_area_ids=(),
            targets={},
        )
        cues = build_situation_episodic_cues(
            runtime_context=rt,
            observation_structured=None,
            latest_action=None,
            encounter_memory=mem,
            encounter_player_id=PID,
            encounter_current_tick=10,
        )
        place_cues = [c for c in cues if c.axis == "place_spot" and c.value == "7"]
        assert len(place_cues) == 1
        # 重複時は先に来た runtime cue が残る (= 既存 dedupe の last-write-wins 反対)
        assert place_cues[0].source == EpisodicCueSource.RUNTIME_CONTEXT


_SPOT_INT_IDS = {"festival_square": 3, "lone_hut": 8}


def _resolve_spot_int_id(spot_str_id: str) -> int:
    return _SPOT_INT_IDS[spot_str_id]


def _encounter_situation_cues(
    mem: InMemoryEncounterMemory,
    *,
    runtime_context=None,  # type: ignore[no-untyped-def]
    observation_structured=None,  # type: ignore[no-untyped-def]
    spot_id_resolver=_resolve_spot_int_id,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    return build_situation_episodic_cues(
        runtime_context=runtime_context,
        observation_structured=observation_structured,
        encounter_memory=mem,
        encounter_player_id=PID,
        encounter_current_tick=10,
        encounter_spot_id_resolver=spot_id_resolver,
    )


class TestEncounterCuesFromRegisteredKeys:
    """Issue #1445: 実際の登録値 (人物は表示名、場所はシナリオの文字列 ID) から encounter cue が作られる。"""

    def test_japanese_display_name_yields_entity_cue(self) -> None:
        """表示名 'ノア' で登録した人物の遭遇から、entity cue 'actor_ノア' が ENCOUNTER source で作られる。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("ノア"), current_tick=10)

        cues = _encounter_situation_cues(mem)

        entity = [c for c in cues if c.axis == "entity"]
        assert [(c.value, c.source) for c in entity] == [
            ("actor_ノア", EpisodicCueSource.ENCOUNTER)
        ]

    def test_display_name_cue_equals_observed_actor_cue(self) -> None:
        """表示名 'ノア' の遭遇から作る entity cue は、観測 structured の actor 'ノア' から作る cue と同じ canonical になり、1 件にまとまる。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("ノア"), current_tick=10)

        cues = _encounter_situation_cues(mem, observation_structured={"actor": "ノア"})

        assert [c.to_canonical() for c in cues if c.axis == "entity"] == ["entity:actor_ノア"]

    def test_different_japanese_names_yield_different_cues(self) -> None:
        """別人の 'ノア' と 'ノエ' の遭遇は、それぞれ別の entity cue になる。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.player("ノア"), current_tick=10)
        mem.observe(PID, EncounterKey.player("ノエ"), current_tick=10)

        cues = _encounter_situation_cues(mem)

        assert sorted(c.value for c in cues if c.axis == "entity") == ["actor_ノア", "actor_ノエ"]

    def test_scenario_spot_id_yields_place_spot_cue_via_resolver(self) -> None:
        """文字列 ID 'festival_square' で登録した場所の遭遇から、resolver が返す数値 ID の place_spot cue '3' が作られる。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.spot("festival_square"), current_tick=10)

        cues = _encounter_situation_cues(mem)

        assert [(c.axis, c.value, c.source) for c in cues] == [
            ("place_spot", "3", EpisodicCueSource.ENCOUNTER)
        ]

    def test_encounter_spot_cue_equals_runtime_place_cue(self) -> None:
        """現在地 spot_id=3 の runtime cue と 'festival_square' の遭遇 cue は同じ canonical になり、place_spot cue は 1 件にまとまる。"""
        from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto

        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.spot("festival_square"), current_tick=10)
        rt = ToolRuntimeContextDto(
            current_spot_id=3,
            current_sub_location_id=None,
            current_area_ids=(),
            targets={},
        )

        cues = _encounter_situation_cues(mem, runtime_context=rt)

        assert [c.to_canonical() for c in cues if c.axis == "place_spot"] == ["place_spot:3"]

    def test_unknown_spot_id_is_skipped_and_other_cues_remain(self) -> None:
        """resolver が知らない場所 ID で例外を投げても、その場所の cue だけを落とし、ほかの遭遇の cue は残る。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.spot("unknown_spot"), current_tick=10)
        mem.observe(PID, EncounterKey.spot("lone_hut"), current_tick=10)

        cues = _encounter_situation_cues(mem)

        assert [c.to_canonical() for c in cues] == ["place_spot:8"]

    def test_spot_id_is_parsed_as_int_when_resolver_absent(self) -> None:
        """resolver を渡さないときは従来どおり、数値文字列の場所 ID '7' を place_spot cue '7' にし、文字列 ID は捨てる。"""
        mem = InMemoryEncounterMemory()
        mem.observe(PID, EncounterKey.spot("7"), current_tick=10)
        mem.observe(PID, EncounterKey.spot("festival_square"), current_tick=10)

        cues = _encounter_situation_cues(mem, spot_id_resolver=None)

        assert [c.to_canonical() for c in cues] == ["place_spot:7"]
