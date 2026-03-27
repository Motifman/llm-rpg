"""Pickle codec helpers for HitBox snapshots."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate


def hit_box_to_blob(hit_box: HitBoxAggregate) -> bytes:
    return pickle.dumps(hit_box, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_hit_box(blob: bytes) -> HitBoxAggregate:
    aggregate = pickle.loads(blob)
    if not isinstance(aggregate, HitBoxAggregate):
        raise TypeError(
            "game_hit_boxes.aggregate_blob does not contain a HitBoxAggregate instance"
        )
    return aggregate


__all__ = ["blob_to_hit_box", "hit_box_to_blob"]
