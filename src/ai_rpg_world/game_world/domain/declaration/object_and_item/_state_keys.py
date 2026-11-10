from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.game_world.domain.exception.object_and_item_declaration_exception import (
    StateKeyDuplicatedException,
    StateKeyOwnerMismatchException,
)
from ai_rpg_world.game_world.domain.value_object import StateKeyId


def require_own_distinct_keys(owner: object, key_owners: Sequence[object], keys: Sequence[StateKeyId]) -> None:
    strangers = [key_owner for key_owner in key_owners if key_owner != owner]
    if strangers:
        raise StateKeyOwnerMismatchException(f"state keys of {owner!r} must belong to it, got keys of {strangers!r}")
    if len(set(keys)) != len(keys):
        raise StateKeyDuplicatedException(
            f"state keys of {owner!r} must not repeat, got {[key.value for key in keys]!r}"
        )
