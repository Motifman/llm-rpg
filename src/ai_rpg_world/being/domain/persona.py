"""Being の人柄。世界が変わっても同じ名前と人柄で入る (#1469)。

人柄そのものは ID を持たないので値オブジェクトにする。プロンプトの文は持たない。文にするのは application の側。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import PersonaValidationException


def _text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PersonaValidationException(f"Persona.{field_name} must be non-blank str")
    return value.strip()


def _optional_text(field_name: str, value: object) -> str | None:
    return None if value is None else _text(field_name, value)


def _texts(field_name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise PersonaValidationException(f"Persona.{field_name} must be tuple")
    return tuple(_text(field_name, item) for item in value)


@dataclass(frozen=True, kw_only=True)
class Persona:
    """名前のほかは、決まっていなければ ``None`` か空にする。決まっていない値を仮の値で埋めない。

    - ``name``: 名乗る名前
    - ``first_person``: 自分を指す一人称
    - ``speech``: 口調
    - ``traits``: 性格
    - ``values``: 大事にしていること
    - ``fears``: 苦手なこと・怖いもの
    - ``background``: 生い立ち
    """

    name: str
    first_person: str | None = None
    speech: str | None = None
    traits: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    fears: tuple[str, ...] = ()
    background: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text("name", self.name))
        for field_name in ("first_person", "speech", "background"):
            object.__setattr__(self, field_name, _optional_text(field_name, getattr(self, field_name)))
        for field_name in ("traits", "values", "fears"):
            object.__setattr__(self, field_name, _texts(field_name, getattr(self, field_name)))


__all__ = ["Persona"]
