"""倒れた身体の場所と時刻を world snapshot で連続させる。"""

from types import SimpleNamespace

from ai_rpg_world.application.being.world_subsystems.fallen_body_codec import (
    FallenBodySubsystemCodec,
)
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def _runtime(registry: FallenBodyRegistry) -> SimpleNamespace:
    return SimpleNamespace(_fallen_body_registry=registry)


class TestFallenBodySubsystemCodec:
    """身体記録の保存と復元を別々に観測できる形で保証する。"""

    def test_capture_writes_location_and_tick(self) -> None:
        """保存 payload に player・場所・倒れた時刻が明示される。"""
        registry = FallenBodyRegistry()
        registry.record(PlayerId(2), SpotId.create(7), WorldTick(13))

        payload = FallenBodySubsystemCodec().capture(_runtime(registry))

        assert payload["entries"] == [
            {"player_id": 2, "spot_id": 7, "downed_at_tick": 13}
        ]

    def test_restore_replaces_the_registry(self) -> None:
        """復元 payload が空の既存 registry に同じ身体記録を戻す。"""
        registry = FallenBodyRegistry()

        FallenBodySubsystemCodec().restore(
            _runtime(registry),
            {
                "schema_version": 1,
                "entries": [
                    {"player_id": 2, "spot_id": 7, "downed_at_tick": 13}
                ],
            },
        )

        record = registry.find(PlayerId(2))
        assert record is not None
        assert record.spot_id == SpotId.create(7)
        assert record.downed_at_tick == WorldTick(13)

    def test_round_trip_is_byte_stable(self) -> None:
        """capture → restore → capture で保存形式も同一になる。"""
        source = FallenBodyRegistry()
        source.record(PlayerId(3), SpotId.create(4), WorldTick(8))
        codec = FallenBodySubsystemCodec()
        payload = codec.capture(_runtime(source))
        restored = FallenBodyRegistry()

        codec.restore(_runtime(restored), payload)

        assert codec.capture(_runtime(restored)) == payload
