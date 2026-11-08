from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusal, CommonRuleRefusalKind
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.action_exception import (
    MissingCommonRuleRefusalTextException,
    UnknownPersonInRefusalTextException,
)
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId

_ACTOR = "actor"


@final
@dataclass(frozen=True)
class RefusalTexts:
    common_rules: Mapping[CommonRuleRefusalKind, TextWithUnassignedPeople]
    world_state: Mapping[RefusalCode, TextWithUnassignedPeople]
    hidden: TextWithUnassignedPeople

    def __post_init__(self) -> None:
        missing = sorted(kind.name for kind in set(CommonRuleRefusalKind) - self.common_rules.keys())
        if missing:
            raise MissingCommonRuleRefusalTextException(f"RefusalTexts.common_rules lacks {missing}")
        for text in (*self.common_rules.values(), *self.world_state.values(), self.hidden):
            unknown = sorted(text.placeholders() - {_ACTOR})
            if unknown:
                raise UnknownPersonInRefusalTextException(
                    f"a refusal text can name only {{{_ACTOR}}}, but {text.template!r} names {unknown}"
                )
        object.__setattr__(self, "common_rules", MappingProxyType(dict(self.common_rules)))
        object.__setattr__(self, "world_state", MappingProxyType(dict(self.world_state)))

    def common_rule_text(self, refusal: CommonRuleRefusal, actor: PersonId) -> TextAboutPeople:
        return _about_actor(self.common_rules[refusal.kind()], actor)


def _about_actor(text: TextWithUnassignedPeople, actor: PersonId) -> TextAboutPeople:
    return text.about({_ACTOR: actor} if _ACTOR in text.placeholders() else {})
