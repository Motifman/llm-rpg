"""Encounter Memory の integration テスト (PR3)。

実 ``WorldRuntime`` を立てて以下を確認する:

- runtime が ``_encounter_memory`` を生成し、observation_appender に collector が
  注入されていること (wiring の end-to-end)
- ``observation_appender.append`` 経由で entity_entered_spot / scenario_event
  観測が来たら encounter が記録されること (= 実 runtime の subsystems を経由
  した wiring 確認)
- snapshot codec list に encounter_memory が含まれ、実 runtime で capture →
  別 runtime で restore の round-trip が動くこと

scenario は ``forbidden_library_demo.json`` (2 player の最小構成) を使う。
LLM 経由の挙動 (=「kaito を実際に reading_room まで移動させて rin に
entity_entered_spot 観測が届く」) はここでは制御せず、observation の入口で
直接注入する。actual な domain event 経路の確認は PR4 で playable test
を回すときに担保する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
)

from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.application.encounter.services.encounter_observation_collector import (
    EncounterObservationCollector,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
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


def _entered_spot_output(actor: str) -> ObservationOutput:
    return ObservationOutput(
        prose=f"{actor} がやってきた。",
        structured={
            "type": "entity_entered_spot",
            "actor": actor,
            "spot_name": "閲覧室",
        },
        observation_category="social",
        schedules_turn=True,
        breaks_movement=False,
    )


def _scenario_event_output(event_id: str, message: str) -> ObservationOutput:
    return ObservationOutput(
        prose=message,
        structured={
            "type": "scenario_event",
            "event_id": event_id,
            "message": message,
        },
        observation_category="environment",
        schedules_turn=True,
        breaks_movement=False,
    )


class TestRuntimeWiring:
    """runtime が ``_encounter_memory`` を持ち、collector が wire されている。"""

    def test_runtime_は__encounter_memory_を_持つ(self) -> None:
        runtime = _create_runtime()
        assert isinstance(runtime._encounter_memory, InMemoryEncounterMemory)

    def test_observation_appender_に_observer_として_collector_が_接続されている(
        self,
    ) -> None:
        """factory function が collector.on_observation を ObservationAppender
        の observer slot に注入する (ObservationAppender 自体は Callable しか
        知らない疎結合な接続)。"""
        runtime = _create_runtime()
        observers = runtime._observation_appender._observers
        assert len(observers) >= 1
        # observer の中に encounter collector の bound method が含まれている
        # ことを「memory 同一性」経由で間接確認する (= bound method 自体は
        # __self__ 経由で EncounterObservationCollector instance を持つ)。
        encounter_observer = next(
            (
                obs
                for obs in observers
                if isinstance(
                    getattr(obs, "__self__", None),
                    EncounterObservationCollector,
                )
            ),
            None,
        )
        assert encounter_observer is not None
        collector = encounter_observer.__self__
        assert collector._memory is runtime._encounter_memory

    def test_初期状態は_spawn_spot_だけが_encounter_に_立つ(self) -> None:
        """PR4 後: 初期 spawn 時に自分の spot encounter が直接記録される。
        forbidden_library_demo では kaito=entrance_hall, rin=reading_room
        が spawn 直後の唯一の encounter。"""
        runtime = _create_runtime()
        kaito = runtime.get_player_ids()[0]
        rin = runtime.get_player_ids()[1]

        kaito_records = runtime._encounter_memory.get_records_for(kaito)
        rin_records = runtime._encounter_memory.get_records_for(rin)
        assert set(kaito_records.keys()) == {
            EncounterKey.spot("entrance_hall")
        }
        assert set(rin_records.keys()) == {EncounterKey.spot("reading_room")}
        # 両方とも初回 (is_first=True) かつ tick=0 で記録される
        assert kaito_records[EncounterKey.spot("entrance_hall")].is_first
        assert rin_records[EncounterKey.spot("reading_room")].is_first


class TestAppenderToEncounterEndToEnd:
    """observation_appender.append 経由で encounter が立つことを確認する。

    本テストは「実 runtime の observation_appender に流せば、wiring を経由して
    encounter_memory に到達する」end-to-end の経路を保証する。
    """

    def test_entity_entered_spot_観測で_player_encounter_が_記録される(
        self,
    ) -> None:
        runtime = _create_runtime()
        rin = runtime.get_player_ids()[1]
        runtime._observation_appender.append(
            rin,
            _entered_spot_output("カイト"),
            datetime.now(timezone.utc),
            None,
        )
        record = runtime._encounter_memory.lookup(
            rin, EncounterKey.player("カイト")
        )
        assert record is not None
        assert record.is_first is True
        # tick は runtime.current_tick() (= 初期 0) で記録される
        assert record.last_seen_tick == runtime.current_tick()

    def test_scenario_event_観測で_event_encounter_が_記録される(
        self,
    ) -> None:
        runtime = _create_runtime()
        kaito = runtime.get_player_ids()[0]
        runtime._observation_appender.append(
            kaito,
            _scenario_event_output("storm_arrives", "嵐が来た"),
            datetime.now(timezone.utc),
            None,
        )
        record = runtime._encounter_memory.lookup(
            kaito, EncounterKey.event("storm_arrives")
        )
        assert record is not None
        assert record.is_first is True

    def test_他_player_は_独立に_encounter_を_持つ(self) -> None:
        runtime = _create_runtime()
        kaito = runtime.get_player_ids()[0]
        rin = runtime.get_player_ids()[1]
        # rin だけが noa を観測
        runtime._observation_appender.append(
            rin,
            _entered_spot_output("ノア"),
            datetime.now(timezone.utc),
            None,
        )
        assert (
            runtime._encounter_memory.lookup(rin, EncounterKey.player("ノア"))
            is not None
        )
        assert (
            runtime._encounter_memory.lookup(
                kaito, EncounterKey.player("ノア")
            )
            is None
        )


class TestSnapshotRoundTripViaRuntime:
    """実 runtime で encounter を蓄積 → snapshot codec で別 runtime に復元できる。

    本テストは Encounter Memory が world snapshot codec list に乗ったこと
    (= _default_codecs に登録された) を integration 経路で確認する。codec
    単体の round-trip は test_encounter_memory_codec.py で別途担保。
    """

    def test_codec_リストに_encounter_memory_が_含まれる(self) -> None:
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            _default_world_subsystem_codecs,
        )

        codec_keys = {c.subsystem_key for c in _default_world_subsystem_codecs()}
        assert "encounter_memory" in codec_keys

    def test_実_runtime_で_capture_して_別_runtime_に_restore_できる(self) -> None:
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            _default_world_subsystem_codecs,
        )

        runtime_a = _create_runtime()
        rin = runtime_a.get_player_ids()[1]
        runtime_a._observation_appender.append(
            rin,
            _entered_spot_output("カイト"),
            datetime.now(timezone.utc),
            None,
        )
        runtime_a._observation_appender.append(
            rin,
            _scenario_event_output("storm_arrives", "嵐"),
            datetime.now(timezone.utc),
            None,
        )

        encounter_codec = next(
            c
            for c in _default_world_subsystem_codecs()
            if c.subsystem_key == "encounter_memory"
        )
        captured = encounter_codec.capture(runtime_a)

        runtime_b = _create_runtime()
        # PR4 後: runtime_b は spawn 直後で rin の spot encounter
        # (reading_room) を持つ。restore で上書きされて runtime_a の
        # encounter (spot + 上で append した player/event) に置き換わる。
        encounter_codec.restore(runtime_b, captured)

        # restore 後の runtime_b で rin の encounter が完全復元
        records = runtime_b._encounter_memory.get_records_for(rin)
        keys = {k.canonical for k in records.keys()}
        assert "player:カイト" in keys
        assert "event:storm_arrives" in keys
