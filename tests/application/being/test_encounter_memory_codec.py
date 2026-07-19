"""``EncounterMemorySubsystemCodec`` の単体テスト (PR2)。

PR2 のスコープは codec の capture / restore round-trip と schema_version
検証のみ。observation pipeline 連携 / runtime への wiring は PR3 で別途。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    EncounterMemorySubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.encounter_memory_codec import (
    SCHEMA_VERSION,
    SUBSYSTEM_KEY,
)
from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _runtime_with(memory: InMemoryEncounterMemory) -> SimpleNamespace:
    """codec が見る runtime の最小 stub。``_encounter_memory`` を持つだけで十分。"""
    return SimpleNamespace(_encounter_memory=memory)


class TestSubsystemKey:
    """subsystem_key と schema_version の不変条件。"""

    def test_subsystem_key_encounter_memory(self) -> None:
        """subsystem key は encounter memory。"""
        assert EncounterMemorySubsystemCodec().subsystem_key == SUBSYSTEM_KEY
        assert SUBSYSTEM_KEY == "encounter_memory"

    def test_initial_schema_version_is_one(self) -> None:
        """初版 schema version は 1。"""
        assert SCHEMA_VERSION == 1


class TestCaptureEmpty:
    """空 memory の capture 挙動。"""

    def test_returns_observe_memory_empty_entries(self) -> None:
        """未 observe の memory は空 entries を返す。"""
        memory = InMemoryEncounterMemory()
        data = EncounterMemorySubsystemCodec().capture(_runtime_with(memory))
        assert data["schema_version"] == 1
        assert data["entries"] == []

    def test_runtime_en_count_er_memory_raises_runtime_error_2(self) -> None:
        """wiring 漏れを silent failure で隠さない (fail-fast)。"""
        runtime = SimpleNamespace()
        with pytest.raises(RuntimeError, match="_encounter_memory"):
            EncounterMemorySubsystemCodec().capture(runtime)


class TestCaptureRestoreRoundTrip:
    """observe 後の record が capture → restore で完全復元されることを確認。"""

    def test_single_player_single_record_round_trip(self) -> None:
        """単一 player 単一 record の round trip。"""
        src = InMemoryEncounterMemory()
        src.observe(PlayerId(1), EncounterKey.player("noa"), current_tick=10)

        captured = EncounterMemorySubsystemCodec().capture(_runtime_with(src))

        dst = InMemoryEncounterMemory()
        EncounterMemorySubsystemCodec().restore(_runtime_with(dst), captured)

        rec = dst.lookup(PlayerId(1), EncounterKey.player("noa"))
        assert rec is not None
        assert rec.count == 1
        assert rec.first_seen_tick == 10
        assert rec.last_seen_tick == 10

    def test_count_first_last_all_restored(self) -> None:
        """observe を 3 回繰り返した record が count=3 / first_seen / last_seen
        ともに復元される。restore で observe() を呼んでしまうと count や
        first_seen が変質するため、内部 store への直書きが正しく機能して
        いることを保証する。"""
        src = InMemoryEncounterMemory()
        src.observe(PlayerId(1), EncounterKey.player("noa"), current_tick=5)
        src.observe(PlayerId(1), EncounterKey.player("noa"), current_tick=42)
        src.observe(PlayerId(1), EncounterKey.player("noa"), current_tick=100)

        captured = EncounterMemorySubsystemCodec().capture(_runtime_with(src))
        dst = InMemoryEncounterMemory()
        EncounterMemorySubsystemCodec().restore(_runtime_with(dst), captured)

        rec = dst.lookup(PlayerId(1), EncounterKey.player("noa"))
        assert rec is not None
        assert rec.count == 3
        assert rec.first_seen_tick == 5
        assert rec.last_seen_tick == 100

    def test_multiple_player_multiple_record_round_trip(self) -> None:
        """複数 player 複数 record の round trip。"""
        src = InMemoryEncounterMemory()
        # player 1: noa (再会) + 森の広場 (初訪問)
        src.observe(PlayerId(1), EncounterKey.player("noa"), current_tick=5)
        src.observe(PlayerId(1), EncounterKey.player("noa"), current_tick=42)
        src.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), current_tick=42)
        # player 2: 嵐 (event-type)
        src.observe(PlayerId(2), EncounterKey.event("storm_arrives"), current_tick=96)

        captured = EncounterMemorySubsystemCodec().capture(_runtime_with(src))

        dst = InMemoryEncounterMemory()
        EncounterMemorySubsystemCodec().restore(_runtime_with(dst), captured)

        # player 1
        noa = dst.lookup(PlayerId(1), EncounterKey.player("noa"))
        assert noa is not None and noa.count == 2 and noa.first_seen_tick == 5
        clearing = dst.lookup(
            PlayerId(1), EncounterKey.spot("forest_clearing")
        )
        assert clearing is not None and clearing.count == 1
        # player 2
        storm = dst.lookup(PlayerId(2), EncounterKey.event("storm_arrives"))
        assert storm is not None and storm.first_seen_tick == 96

    def test_clears_and_restores_restore_existing_record(self) -> None:
        """部分復元による不整合を防ぐ (= save 時点での状態に完全に戻す)。"""
        src = InMemoryEncounterMemory()
        src.observe(PlayerId(1), EncounterKey.player("noa"), current_tick=5)

        captured = EncounterMemorySubsystemCodec().capture(_runtime_with(src))

        dst = InMemoryEncounterMemory()
        # 別 player の record を先に入れておく → restore で消えるはず
        dst.observe(PlayerId(99), EncounterKey.spot("nowhere"), current_tick=0)

        EncounterMemorySubsystemCodec().restore(_runtime_with(dst), captured)

        # restore 後、player 99 の record は消えている
        assert dst.lookup(PlayerId(99), EncounterKey.spot("nowhere")) is None
        # player 1 の record は復元されている
        assert dst.lookup(PlayerId(1), EncounterKey.player("noa")) is not None

    def test_records_deterministic_order_dump_entries(self) -> None:
        """snapshot diff の noise を減らすため。player_id 昇順 / canonical key 昇順。"""
        src = InMemoryEncounterMemory()
        # 故意に挿入順を逆順にしても dump は sort される
        src.observe(PlayerId(2), EncounterKey.player("zzz"), current_tick=0)
        src.observe(PlayerId(2), EncounterKey.player("aaa"), current_tick=0)
        src.observe(PlayerId(1), EncounterKey.spot("xxx"), current_tick=0)

        data = EncounterMemorySubsystemCodec().capture(_runtime_with(src))

        # player_id 昇順
        pids = [e["player_id"] for e in data["entries"]]
        assert pids == sorted(pids)
        # 各 entry 内の records も canonical key 昇順
        for e in data["entries"]:
            keys = [r["key"] for r in e["records"]]
            assert keys == sorted(keys)


class TestRestoreSchemaCompatibility:
    """schema_version の forward-compat / 後方互換。"""

    def test_schema_version_raises_exception(self) -> None:
        """未サポート schemaversion は例外。"""
        memory = InMemoryEncounterMemory()
        with pytest.raises(ValueError, match="schema_version"):
            EncounterMemorySubsystemCodec().restore(
                _runtime_with(memory),
                {"schema_version": 999, "entries": []},
            )

    def test_runtime_en_count_er_memory_raises_runtime_error(self) -> None:
        """runtime に の encountermemory が無ければ RuntimeError。"""
        runtime = SimpleNamespace()
        with pytest.raises(RuntimeError, match="_encounter_memory"):
            EncounterMemorySubsystemCodec().restore(
                runtime,
                {"schema_version": 1, "entries": []},
            )

    def test_entries_key_missing_empty_does_not_crash(self) -> None:
        """forward-compat: 上位 schema が entries を出さない場合の防衛。"""
        memory = InMemoryEncounterMemory()
        EncounterMemorySubsystemCodec().restore(
            _runtime_with(memory),
            {"schema_version": 1},  # entries 無し
        )
        # 復元後は空のはず
        assert memory.get_records_for(PlayerId(1)) == {}

    def test_different_ien_count_er_memory_raises_not_implemented_error(self) -> None:
        """``InMemoryEncounterMemory`` 以外を渡すと dead silent fallback ではなく
        明示的に NotImplementedError を投げる (= silent failure 防止)。"""

        class _DummyMemory:
            pass

        runtime = SimpleNamespace(_encounter_memory=_DummyMemory())
        with pytest.raises(NotImplementedError, match="InMemoryEncounterMemory"):
            EncounterMemorySubsystemCodec().capture(runtime)
        with pytest.raises(NotImplementedError, match="InMemoryEncounterMemory"):
            EncounterMemorySubsystemCodec().restore(
                runtime, {"schema_version": 1, "entries": []}
            )


class TestRestoreInvalidPayloadSurfacesDomainException:
    """不正 payload が ``EncounterRecord`` の不変条件で fail-fast することを確認。

    silent failure (= 不正な count=0 などを通してしまう) を防ぐ。codec で
    例外を握り潰していないことを保証する。
    """

    def test_count_zero_record_validation_raises_validation_exception(self) -> None:
        """count 0 の record は validation 例外を 投げる。"""
        from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
            EncounterRecordValidationException,
        )

        memory = InMemoryEncounterMemory()
        with pytest.raises(EncounterRecordValidationException, match="count"):
            EncounterMemorySubsystemCodec().restore(
                _runtime_with(memory),
                {
                    "schema_version": 1,
                    "entries": [
                        {
                            "player_id": 1,
                            "records": [
                                {
                                    "key": "player:noa",
                                    "first_seen_tick": 0,
                                    "last_seen_tick": 0,
                                    "count": 0,
                                }
                            ],
                        }
                    ],
                },
            )

    def test_first_seen_last_seen_record_validation_raises_validation_exception(
        self,
    ) -> None:
        """first seen が last seen より 大きい record は validation 例外を 投げる。"""
        from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
            EncounterRecordValidationException,
        )

        memory = InMemoryEncounterMemory()
        with pytest.raises(
            EncounterRecordValidationException, match="last_seen_tick"
        ):
            EncounterMemorySubsystemCodec().restore(
                _runtime_with(memory),
                {
                    "schema_version": 1,
                    "entries": [
                        {
                            "player_id": 1,
                            "records": [
                                {
                                    "key": "player:noa",
                                    "first_seen_tick": 10,
                                    "last_seen_tick": 5,
                                    "count": 2,
                                }
                            ],
                        }
                    ],
                },
            )

    def test_invalid_canonical_key_validation_raises_validation_exception(self) -> None:
        """不正な canonical key は validation 例外を 投げる。"""
        from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
            EncounterKeyValidationException,
        )

        memory = InMemoryEncounterMemory()
        with pytest.raises(EncounterKeyValidationException, match="canonical"):
            EncounterMemorySubsystemCodec().restore(
                _runtime_with(memory),
                {
                    "schema_version": 1,
                    "entries": [
                        {
                            "player_id": 1,
                            "records": [
                                {
                                    "key": "no_separator_here",
                                    "first_seen_tick": 0,
                                    "last_seen_tick": 0,
                                    "count": 1,
                                }
                            ],
                        }
                    ],
                },
            )
