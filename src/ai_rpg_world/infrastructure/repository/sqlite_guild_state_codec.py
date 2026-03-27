"""Helpers for normalizing guild aggregates into SQLite rows."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def build_guild(
    *,
    guild_id: int,
    spot_id: int,
    location_area_id: int,
    name: str,
    description: str,
    member_rows: Iterable[tuple[int, str, str, int]],
) -> GuildAggregate:
    members = {
        PlayerId(player_id): GuildMembership(
            player_id=PlayerId(player_id),
            role=GuildRole(role),
            joined_at=datetime.fromisoformat(joined_at),
            contribution_points=contribution_points,
        )
        for player_id, role, joined_at, contribution_points in member_rows
    }
    return GuildAggregate(
        guild_id=GuildId(guild_id),
        spot_id=SpotId(spot_id),
        location_area_id=LocationAreaId(location_area_id),
        name=name,
        description=description,
        members=members,
    )

