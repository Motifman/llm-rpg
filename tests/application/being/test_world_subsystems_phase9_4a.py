"""Phase 9-4a codec の単体テスト (active_effects / attention / pursuit / spot_nav)。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    PlayerActiveEffectsSubsystemCodec,
    PlayerAttentionLevelSubsystemCodec,
    PlayerPursuitStateSubsystemCodec,
    PlayerSpotNavigationStateSubsystemCodec,
)
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_pursuit_state import (
    PlayerPursuitState,
)
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.value_object.connection_id import (
    ConnectionId,
)


def _repo_stub(initial: dict[PlayerId, Any]):
    return SimpleNamespace(
        find_by_id=lambda pid: initial.get(pid),
        save=lambda agg: initial.update({_pid_of(agg): agg}),
        _store=initial,
    )


def _pid_of(agg: Any) -> PlayerId:
    """test stub のための player_id 取得 — SimpleNamespace に _player_id を仕込む。"""
    return getattr(agg, "_player_id", PlayerId(1))


def _runtime_for_player(repo_stub) -> Any:
    return SimpleNamespace(
        _player_status_repo=repo_stub,
        get_player_ids=lambda: list(repo_stub._store.keys()),
    )


def _make_status_agg(*, attention=AttentionLevel.FULL, effects=None) -> Any:
    agg = SimpleNamespace()
    agg._player_id = PlayerId(1)
    agg._active_effects = list(effects or [])
    agg._attention_level = attention
    agg._pursuit_state = PlayerPursuitState.empty()
    agg._spot_navigation_state = None
    agg._events = []
    return agg


class TestActiveEffectsCodec:
    """active_effects 往復。"""

    def test_capture_restore_round_trip(self) -> None:
        src_agg = _make_status_agg(
            effects=[
                StatusEffect(
                    effect_type=StatusEffectType.ATTACK_UP,
                    value=1.2,
                    expiry_tick=WorldTick(100),
                ),
                StatusEffect(
                    effect_type=StatusEffectType.POISON,
                    value=0.5,
                    expiry_tick=WorldTick(50),
                ),
            ]
        )
        src_repo = _repo_stub({PlayerId(1): src_agg})
        captured = PlayerActiveEffectsSubsystemCodec().capture(
            _runtime_for_player(src_repo)
        )
        assert len(captured["entries"][0]["effects"]) == 2

        dst_agg = _make_status_agg()  # 空 effects
        dst_repo = _repo_stub({PlayerId(1): dst_agg})
        PlayerActiveEffectsSubsystemCodec().restore(
            _runtime_for_player(dst_repo), captured
        )
        assert len(dst_agg._active_effects) == 2
        assert dst_agg._active_effects[0].effect_type == StatusEffectType.ATTACK_UP
        assert dst_agg._active_effects[0].value == 1.2

    def test_empty_effects_works(self) -> None:
        """空 effects でも 動く。"""
        agg = _make_status_agg(effects=[])
        repo = _repo_stub({PlayerId(1): agg})
        captured = PlayerActiveEffectsSubsystemCodec().capture(
            _runtime_for_player(repo)
        )
        assert captured["entries"][0]["effects"] == []


class TestAttentionLevelCodec:
    def test_capture_restore_round_trip_2(self) -> None:
        src_agg = _make_status_agg(attention=AttentionLevel.FILTER_SOCIAL)
        captured = PlayerAttentionLevelSubsystemCodec().capture(
            _runtime_for_player(_repo_stub({PlayerId(1): src_agg}))
        )
        assert captured["entries"][0]["attention_level"] == "FILTER_SOCIAL"

        dst_agg = _make_status_agg(attention=AttentionLevel.FULL)
        dst_repo = _repo_stub({PlayerId(1): dst_agg})
        PlayerAttentionLevelSubsystemCodec().restore(
            _runtime_for_player(dst_repo), captured
        )
        assert dst_agg._attention_level == AttentionLevel.FILTER_SOCIAL


class TestPursuitStateCodec:
    def test_pursuit_none_round_trips(self) -> None:
        """pursuitNone は None で往復。"""
        src_agg = _make_status_agg()
        captured = PlayerPursuitStateSubsystemCodec().capture(
            _runtime_for_player(_repo_stub({PlayerId(1): src_agg}))
        )
        assert captured["entries"][0]["pursuit"] is None

    def test_active_pursuit_round_trips(self) -> None:
        """activepursuit を往復。"""
        pursuit = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=PursuitTargetSnapshot(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(x=10, y=20, z=0),
            ),
            last_known=PursuitLastKnownState(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(x=10, y=20),
                observed_at_tick=WorldTick(7),
            ),
            failure_reason=None,
        )
        src_agg = _make_status_agg()
        src_agg._pursuit_state = PlayerPursuitState(pursuit=pursuit)
        captured = PlayerPursuitStateSubsystemCodec().capture(
            _runtime_for_player(_repo_stub({PlayerId(1): src_agg}))
        )

        dst_agg = _make_status_agg()
        dst_repo = _repo_stub({PlayerId(1): dst_agg})
        PlayerPursuitStateSubsystemCodec().restore(
            _runtime_for_player(dst_repo), captured
        )
        restored = dst_agg._pursuit_state.pursuit
        assert restored is not None
        assert restored.actor_id == WorldObjectId(1)
        assert restored.target_id == WorldObjectId(2)
        assert restored.target_snapshot.coordinate.x == 10
        assert restored.last_known.observed_at_tick == WorldTick(7)

    def test_failure_reason_round_trips(self) -> None:
        """failure reason の往復。"""
        # PursuitState の invariant: target_snapshot か last_known 必須
        pursuit = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            last_known=PursuitLastKnownState(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(x=0, y=0),
            ),
            failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
        )
        src_agg = _make_status_agg()
        src_agg._pursuit_state = PlayerPursuitState(pursuit=pursuit)
        captured = PlayerPursuitStateSubsystemCodec().capture(
            _runtime_for_player(_repo_stub({PlayerId(1): src_agg}))
        )
        assert (
            captured["entries"][0]["pursuit"]["failure_reason"]
            == "path_unreachable"
        )


class TestSpotNavigationStateCodec:
    def test_rest_round_trips(self) -> None:
        """atrest を往復。"""
        sn = PlayerSpotNavigationState.at_rest(spot_id=SpotId(1))
        src_agg = _make_status_agg()
        src_agg._spot_navigation_state = sn
        captured = PlayerSpotNavigationStateSubsystemCodec().capture(
            _runtime_for_player(_repo_stub({PlayerId(1): src_agg}))
        )
        assert captured["entries"][0]["state"]["is_traveling"] is False
        assert captured["entries"][0]["state"]["current_spot_id"] == 1

        dst_agg = _make_status_agg()
        dst_repo = _repo_stub({PlayerId(1): dst_agg})
        PlayerSpotNavigationStateSubsystemCodec().restore(
            _runtime_for_player(dst_repo), captured
        )
        assert dst_agg._spot_navigation_state.current_spot_id == SpotId(1)
        assert dst_agg._spot_navigation_state.is_traveling is False

    def test_traveling_state_round_trips(self) -> None:
        """travelingstate を往復。"""
        sn = PlayerSpotNavigationState(
            current_spot_id=SpotId(1),
            current_sub_location_id=None,
            is_traveling=True,
            route=(SpotId(1), SpotId(2), SpotId(3)),
            leg_index=0,
            leg_connection_ids=(ConnectionId(10), ConnectionId(20)),
            leg_travel_ticks=(3, 5),
            ticks_remaining_on_current_leg=2,
        )
        src_agg = _make_status_agg()
        src_agg._spot_navigation_state = sn
        captured = PlayerSpotNavigationStateSubsystemCodec().capture(
            _runtime_for_player(_repo_stub({PlayerId(1): src_agg}))
        )

        dst_agg = _make_status_agg()
        dst_repo = _repo_stub({PlayerId(1): dst_agg})
        PlayerSpotNavigationStateSubsystemCodec().restore(
            _runtime_for_player(dst_repo), captured
        )
        restored = dst_agg._spot_navigation_state
        assert restored.is_traveling is True
        assert restored.route == (SpotId(1), SpotId(2), SpotId(3))
        assert restored.ticks_remaining_on_current_leg == 2
        assert restored.leg_travel_ticks == (3, 5)

    def test_none_state_round_trips(self) -> None:
        """Nonestate を往復。"""
        src_agg = _make_status_agg()
        src_agg._spot_navigation_state = None
        captured = PlayerSpotNavigationStateSubsystemCodec().capture(
            _runtime_for_player(_repo_stub({PlayerId(1): src_agg}))
        )
        assert captured["entries"][0]["state"] is None


class TestUnsupportedSchemaVersion:
    @pytest.mark.parametrize(
        "codec_cls",
        [
            PlayerActiveEffectsSubsystemCodec,
            PlayerAttentionLevelSubsystemCodec,
            PlayerPursuitStateSubsystemCodec,
            PlayerSpotNavigationStateSubsystemCodec,
        ],
    )
    def test_unsupported_schema_version_raises_exception(self, codec_cls) -> None:
        """未サポート schemaversion は例外。"""
        codec = codec_cls()
        with pytest.raises(ValueError, match="schema_version"):
            codec.restore(SimpleNamespace(), {"schema_version": 999})
