from types import SimpleNamespace

from ai_rpg_world.application.being.world_subsystems.departed_position_codec import DepartedPositionSubsystemCodec
from ai_rpg_world.application.player.services.departed_position_store import DepartedPositionStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class TestDepartedPositionSubsystemCodec:
    """去った主体の位置が world snapshot を挟んでも連続することを保証する。"""

    def test_position_survives_a_snapshot_round_trip(self) -> None:
        """保存した player と spot の対応を、新しい store へ完全に復元する。"""
        source = DepartedPositionStore()
        source.place(PlayerId(2), SpotId.create(20))
        codec = DepartedPositionSubsystemCodec()
        payload = codec.capture(SimpleNamespace(_departed_position_store=source))
        restored = DepartedPositionStore()

        codec.restore(SimpleNamespace(_departed_position_store=restored), payload)

        assert restored.snapshot() == {PlayerId(2): SpotId.create(20)}

    def test_restore_replaces_positions_without_emitting_callbacks(self) -> None:
        """復元は既存値へ追記せず、payload が表す全体へ置き換える。"""
        store = DepartedPositionStore()
        store.place(PlayerId(1), SpotId.create(10))

        DepartedPositionSubsystemCodec().restore(
            SimpleNamespace(_departed_position_store=store),
            {"schema_version": 1, "entries": [{"player_id": 2, "spot_id": 20}]},
        )

        assert store.snapshot() == {PlayerId(2): SpotId.create(20)}
