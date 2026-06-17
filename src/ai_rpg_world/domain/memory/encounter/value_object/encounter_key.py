"""``EncounterKey``: 「自分が触れた何か」を一意に指す Value Object。

設計判断 (docs/memory_system/perception_memory_join_design.md):

- Encounter Memory は entity / spot / event-type の 3 種に対称的に familiarity を
  記録する。それぞれを区別するため、kind と identifier の 2 軸を持つ
- kind は ``"player"`` / ``"spot"`` / ``"event"`` 等の prefix string。Engine 側で
  enum 固定にはせず、後から ``"object"`` / ``"weather"`` / ``"emotion"`` を加えても
  互換が壊れない polymorphic な string にする
- canonical 表現は ``f"{kind}:{identifier}"``。snapshot / trace / log の何処でも
  この形で出るようにし、人間が grep しやすくする
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, FrozenSet

from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
    EncounterKeyValidationException,
)


# canonical separator。kind と identifier 自身がこれを含むことは禁止する。
_SEPARATOR = ":"


@dataclass(frozen=True)
class EncounterKey:
    """encounter の対象を識別する key (kind + identifier)。

    例:
        >>> EncounterKey.player("noa").canonical
        'player:noa'
        >>> EncounterKey.spot("forest_clearing").canonical
        'spot:forest_clearing'
        >>> EncounterKey.event("storm_arrives").canonical
        'event:storm_arrives'
    """

    kind: str
    identifier: str

    #: 既知の kind 一覧。未知 kind を拒否するのではなく、後方互換を保ちつつ
    #: 「想定されている kind」を明示するための参考値。
    KNOWN_KINDS: ClassVar[FrozenSet[str]] = frozenset(
        {"player", "spot", "event", "object", "weather", "emotion"}
    )

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str):
            raise EncounterKeyValidationException("kind must be str")
        if not isinstance(self.identifier, str):
            raise EncounterKeyValidationException("identifier must be str")
        kind = self.kind
        identifier = self.identifier
        if not kind.strip():
            raise EncounterKeyValidationException("kind must be non-empty")
        if not identifier.strip():
            raise EncounterKeyValidationException("identifier must be non-empty")
        if _SEPARATOR in kind:
            raise EncounterKeyValidationException(
                f"kind must not contain {_SEPARATOR!r} (kind={kind!r})"
            )
        if _SEPARATOR in identifier:
            raise EncounterKeyValidationException(
                f"identifier must not contain {_SEPARATOR!r} "
                f"(identifier={identifier!r})"
            )

    @property
    def canonical(self) -> str:
        """``"kind:identifier"`` 形式の canonical string。"""
        return f"{self.kind}{_SEPARATOR}{self.identifier}"

    # ────────────────────────────────────────────────────────
    # Factory: 既知 kind に対する型安全な builder
    # ────────────────────────────────────────────────────────

    @classmethod
    def player(cls, identifier: str) -> "EncounterKey":
        return cls(kind="player", identifier=identifier)

    @classmethod
    def spot(cls, identifier: str) -> "EncounterKey":
        return cls(kind="spot", identifier=identifier)

    @classmethod
    def event(cls, identifier: str) -> "EncounterKey":
        return cls(kind="event", identifier=identifier)

    @classmethod
    def from_canonical(cls, canonical: str) -> "EncounterKey":
        """``"kind:identifier"`` 文字列を parse する。

        Raises:
            EncounterKeyValidationException: separator が無い / kind / identifier
                が空 / 不正形式。
        """
        if not isinstance(canonical, str):
            raise EncounterKeyValidationException("canonical must be str")
        if _SEPARATOR not in canonical:
            raise EncounterKeyValidationException(
                f"canonical must contain {_SEPARATOR!r} (got {canonical!r})"
            )
        kind, identifier = canonical.split(_SEPARATOR, 1)
        # __post_init__ で validation される
        return cls(kind=kind, identifier=identifier)


__all__ = ["EncounterKey"]
