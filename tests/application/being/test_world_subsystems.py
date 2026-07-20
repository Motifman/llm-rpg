"""Phase 9-2 subsystem codec の単体テスト。

各 codec が独立して capture / restore できることを担保する。
runtime は最小 stub を組んで本物の runtime を立てない。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    PendingFoodSpoilageSubsystemCodec,
    PlayerNeedsSubsystemCodec,
    PlayerPositionSubsystemCodec,
    PlayerVitalsSubsystemCodec,
    WorldTickSubsystemCodec,
)
from ai_rpg_world.application.being.experiment_snapshot_session import (
    _default_world_subsystem_codecs,
)
from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType
from ai_rpg_world.domain.player.value_object.agent_needs import AgentNeeds
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


class TestPendingFoodSpoilageCodec:
    """未通知の腐敗集約バッファが snapshot 再開後も失われないことを保証する。"""

    def test_capture_restore_round_trip(self) -> None:
        """当日分の未通知腐敗バッファを capture → restore で保持する。"""
        codec = PendingFoodSpoilageSubsystemCodec()
        src_runtime = SimpleNamespace(
            _pending_spoiled={
                7: {
                    "spec_id": 7,
                    "spec_name": "野いちご",
                    "instance_ids": [101, 102],
                },
                3: {
                    "spec_id": 3,
                    "spec_name": "貝",
                    "instance_ids": [201],
                },
            },
            _pending_spoiled_day=2,
        )

        captured = codec.capture(src_runtime)
        assert [entry["spec_id"] for entry in captured["entries"]] == [3, 7]
        assert captured["entries"][1]["instance_ids"] == [101, 102]

        dst_runtime = SimpleNamespace(_pending_spoiled={}, _pending_spoiled_day=None)
        codec.restore(dst_runtime, captured)

        assert dst_runtime._pending_spoiled_day == 2
        assert dst_runtime._pending_spoiled == {
            3: {
                "spec_id": 3,
                "spec_name": "貝",
                "instance_ids": [201],
            },
            7: {
                "spec_id": 7,
                "spec_name": "野いちご",
                "instance_ids": [101, 102],
            },
        }

    def test_restored_buffer_flushes_food_spoiled_observation(self) -> None:
        """restore 後の既存 flush 経路で、再開前に積まれた腐敗通知が配信される。"""
        from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime

        codec = PendingFoodSpoilageSubsystemCodec()
        runtime = SimpleNamespace(_pending_spoiled={}, _pending_spoiled_day=None)
        codec.restore(
            runtime,
            {
                "schema_version": 1,
                "pending_day": 4,
                "entries": [
                    {
                        "spec_id": 7,
                        "spec_name": "野いちご",
                        "instance_ids": [101, 102],
                    }
                ],
            },
        )
        emitted: list[tuple[PlayerId, Any]] = []
        runtime.get_player_ids = lambda: [PlayerId(1), PlayerId(2)]
        runtime._emit_observation_directly = (
            lambda player_id, output: emitted.append((player_id, output))
        )

        WorldRuntime._flush_pending_food_spoiled(runtime)

        assert [pid for pid, _ in emitted] == [PlayerId(1), PlayerId(2)]
        assert emitted[0][1].structured == {
            "type": "food_spoiled",
            "aggregation": "daily",
            "day": 4,
            "spec_summary": [
                {
                    "item_spec_id": 7,
                    "spec_name": "野いちご",
                    "count": 2,
                }
            ],
            "item_instance_ids": [101, 102],
        }
        assert runtime._pending_spoiled == {}
        assert runtime._pending_spoiled_day is None

    def test_default_world_subsystem_codecs_include_pending_food_spoilage(self) -> None:
        """既定 world snapshot に未通知腐敗バッファ codec が登録される。"""
        keys = [codec.subsystem_key for codec in _default_world_subsystem_codecs()]
        assert keys[-1] == "pending_food_spoilage"


class TestWorldTickCodec:
    """world_tick の save / restore。"""

    def test_capture_restore_round_trip(self) -> None:
        provider = InMemoryGameTimeProvider(initial_tick=42)
        runtime = SimpleNamespace(_time_provider=provider)
        codec = WorldTickSubsystemCodec()
        captured = codec.capture(runtime)
        assert captured["world_tick"] == 42

        # 別 provider に restore
        new_provider = InMemoryGameTimeProvider(initial_tick=0)
        new_runtime = SimpleNamespace(_time_provider=new_provider)
        codec.restore(new_runtime, captured)
        assert new_provider.get_current_tick().value == 42

    def test_subsystem_key_world_tick(self) -> None:
        """subsystem key は world tick。"""
        assert WorldTickSubsystemCodec().subsystem_key == "world_tick"

    def test_unsupported_schema_version_raises_exception(self) -> None:
        """unsupportedschemaversion は例外。"""
        provider = InMemoryGameTimeProvider()
        runtime = SimpleNamespace(_time_provider=provider)
        with pytest.raises(ValueError, match="schema_version"):
            WorldTickSubsystemCodec().restore(
                runtime, {"schema_version": 999, "world_tick": 1}
            )

    def test_set_current_tick_negative_raises_value_error(self) -> None:
        """setcurrenttick の負値は ValueError。"""
        provider = InMemoryGameTimeProvider()
        with pytest.raises(ValueError):
            provider.set_current_tick(-1)


class TestPlayerVitalsCodec:
    """HP / MP / Stamina / Gold / is_down の save / restore。"""

    def _make_agg_stub(
        self,
        *,
        player_id: int = 1,
        hp: int = 100,
        hp_max: int = 100,
    ) -> Any:
        """PlayerStatusAggregate 風の stub (= private attribute だけ要る)。"""
        agg = SimpleNamespace()
        agg._hp = Hp(value=hp, max_hp=hp_max)
        agg._mp = Mp(value=50, max_mp=80)
        agg._stamina = Stamina(value=70, max_stamina=100)
        agg._gold = Gold(value=42)
        agg._is_down = False
        agg._events = []
        return agg

    def test_capture_restore_round_trip_2(self) -> None:
        src_agg = self._make_agg_stub(hp=75)
        repo: dict[PlayerId, Any] = {PlayerId(1): src_agg}

        def find_by_id(pid: PlayerId) -> Any:
            return repo.get(pid)

        def save(agg: Any) -> None:
            repo[PlayerId(1)] = agg

        src_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=find_by_id, save=save
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        captured = PlayerVitalsSubsystemCodec().capture(src_runtime)
        assert captured["entries"][0]["hp_value"] == 75

        # 別 stub に restore
        dst_agg = self._make_agg_stub(hp=100)
        dst_repo: dict[PlayerId, Any] = {PlayerId(1): dst_agg}
        dst_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: dst_repo.get(pid),
                save=lambda agg: dst_repo.update({PlayerId(1): agg}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        PlayerVitalsSubsystemCodec().restore(dst_runtime, captured)
        assert dst_repo[PlayerId(1)]._hp.value == 75


class TestPlayerNeedsCodec:
    """AgentNeeds (= HUNGER / FATIGUE) の save / restore。"""

    def test_capture_restore_round_trip_3(self) -> None:
        agg = SimpleNamespace()
        agg._needs = AgentNeeds.default(max_value=100).with_updated(
            AgentNeed.create(NeedType.HUNGER, 65, 100)
        )
        agg._events = []
        src_repo: dict[PlayerId, Any] = {PlayerId(1): agg}
        src_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: src_repo.get(pid),
                save=lambda a: src_repo.update({PlayerId(1): a}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        captured = PlayerNeedsSubsystemCodec().capture(src_runtime)
        assert captured["entries"][0]["needs"][0]["need_type"] == "HUNGER"

        dst_agg = SimpleNamespace()
        dst_agg._needs = AgentNeeds.default(max_value=100)
        dst_agg._events = []
        dst_repo: dict[PlayerId, Any] = {PlayerId(1): dst_agg}
        dst_runtime = SimpleNamespace(
            _player_status_repo=SimpleNamespace(
                find_by_id=lambda pid: dst_repo.get(pid),
                save=lambda a: dst_repo.update({PlayerId(1): a}),
            ),
            get_player_ids=lambda: [PlayerId(1)],
        )
        PlayerNeedsSubsystemCodec().restore(dst_runtime, captured)
        hunger = dst_repo[PlayerId(1)]._needs.get(NeedType.HUNGER)
        assert hunger is not None
        assert hunger.value == 65


class TestPlayerPositionCodec:
    """spot_id の save / restore (= 内部 dict 直接書き換え)。"""

    def test_capture_all_player_spot_id(self) -> None:
        """capture は全 player の spotid を集める。"""
        # runtime stub: get_player_ids + get_player_spot_id を持つ
        runtime = SimpleNamespace(
            _spot_graph_repo=SimpleNamespace(
                find_graph=lambda: SimpleNamespace()
            ),
            get_player_ids=lambda: [PlayerId(1), PlayerId(2)],
            get_player_spot_id=lambda pid: "spot_a" if pid.value == 1 else "spot_b",
        )
        captured = PlayerPositionSubsystemCodec().capture(runtime)
        assert captured["entries"][0]["spot_id"] == "spot_a"
        assert captured["entries"][1]["spot_id"] == "spot_b"


class TestCodecsKeysAreUnique:
    """4 codec の subsystem_key が衝突していないことを担保。"""

    def test_all_keys_unique(self) -> None:
        """全keys が unique。"""
        keys = [
            WorldTickSubsystemCodec().subsystem_key,
            PlayerPositionSubsystemCodec().subsystem_key,
            PlayerVitalsSubsystemCodec().subsystem_key,
            PlayerNeedsSubsystemCodec().subsystem_key,
        ]
        assert len(set(keys)) == len(keys)
