"""BeingIdentity — persona の不変核 (= name / first_person)。

PR #462 §2.1 (R1) の Being 集約構成要素:

    identity: persona 不変核 (名前 / 第一人称 / 価値プロファイル)

本 PR (Phase 2 PR1) では **最小限の不変核** (name + first_person) のみを表現する。
価値プロファイルや好み等の拡張は後続 PR で `domain/persona/` (= Phase 1 PR4 で
昇格済の AgentPersonaDto / PersonaPromptPolicy) との接続として導入する。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingIdentityValidationException,
)


@dataclass(frozen=True)
class BeingIdentity:
    """Being の不変核を表す値オブジェクト。

    - ``name``: 一人称的に名乗る固有名 (例: 「アダ」「タカシ」)
    - ``first_person``: その Being が自分を指すときの一人称代名詞
      (例: 「わたし」「俺」「I」)
    """

    name: str
    first_person: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self._strip_and_validate("name", self.name))
        object.__setattr__(
            self,
            "first_person",
            self._strip_and_validate("first_person", self.first_person),
        )

    @staticmethod
    def _strip_and_validate(field_name: str, value: object) -> str:
        if not isinstance(value, str):
            raise BeingIdentityValidationException(
                f"BeingIdentity.{field_name} must be str, got {type(value).__name__}"
            )
        stripped = value.strip()
        if not stripped:
            raise BeingIdentityValidationException(
                f"BeingIdentity.{field_name} must be non-empty"
            )
        return stripped


__all__ = ["BeingIdentity"]
