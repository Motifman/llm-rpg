"""Pickle codec helpers for MonsterTemplate snapshots."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate


def monster_template_to_blob(template: MonsterTemplate) -> bytes:
    return pickle.dumps(template, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_monster_template(blob: bytes) -> MonsterTemplate:
    template = pickle.loads(blob)
    if not isinstance(template, MonsterTemplate):
        raise TypeError(
            "game_monster_templates.aggregate_blob does not contain a MonsterTemplate instance"
        )
    return template


__all__ = ["blob_to_monster_template", "monster_template_to_blob"]
