"""Pickle codec helpers for LocationEstablishment snapshots."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)


def location_establishment_to_blob(
    aggregate: LocationEstablishmentAggregate,
) -> bytes:
    return pickle.dumps(aggregate, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_location_establishment(blob: bytes) -> LocationEstablishmentAggregate:
    aggregate = pickle.loads(blob)
    if not isinstance(aggregate, LocationEstablishmentAggregate):
        raise TypeError(
            "game_location_establishments.aggregate_blob does not contain a LocationEstablishmentAggregate instance"
        )
    return aggregate


__all__ = ["blob_to_location_establishment", "location_establishment_to_blob"]
