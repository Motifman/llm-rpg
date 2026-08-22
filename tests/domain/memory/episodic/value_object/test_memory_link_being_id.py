"""MemoryLink が経験の主体 BeingId を必須で持つことを保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)

_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _link(**overrides) -> MemoryLink:
    base = dict(
        link_id="mlk-1",
        player_id=1,
        episode_id_a="a",
        episode_id_b="b",
        link_type=MemoryLinkType.CO_RECALL,
        strength=0.9,
        co_activation_count=1,
        created_at=_NOW,
        last_activated_at=_NOW,
        decay_rate=0.001,
    )
    base.update(overrides)
    if "being_id" not in overrides:
        base["being_id"] = BeingId(f"being_w1_p{base['player_id']}")
    return MemoryLink(**base)


class TestMemoryLinkBeingId:
    """being_id 必須と型検証を保証する。"""

    def test_being_id_is_required(self) -> None:
        """being_id を欠くと dataclass 必須フィールドとして TypeError になる。"""
        with pytest.raises(TypeError):
            MemoryLink(
                link_id="mlk-1",
                player_id=1,
                episode_id_a="a",
                episode_id_b="b",
                link_type=MemoryLinkType.CO_RECALL,
                strength=0.9,
                co_activation_count=1,
                created_at=_NOW,
                last_activated_at=_NOW,
                decay_rate=0.001,
            )

    def test_non_being_id_raises_type_error(self) -> None:
        """being_id に BeingId 以外を渡すと TypeError になる。"""
        with pytest.raises(TypeError, match="being_id must be BeingId"):
            _link(being_id="not-a-being-id")  # type: ignore[arg-type]

    def test_player_id_remains_int(self) -> None:
        """player_id は attach 元の身体として int のまま残る。"""
        link = _link(player_id=42)
        assert link.player_id == 42
        assert link.being_id == BeingId("being_w1_p42")
