"""書き起こしの材料を、Being が自分の人柄と居場所から引く。

人格の文は【ペルソナ】と同じ文にする。行動を選ぶときと書き起こすときで、自分の像が食い違わないように。
"""

from __future__ import annotations

from ai_rpg_world.being.application.current_working_memory import BeingLookup
from ai_rpg_world.being.application.handlers.write_episodes_handler import EpisodeWritingCircumstances
from ai_rpg_world.being.application.persona_text import persona_text_of
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona


class CircumstancesOfBeings:
    def __init__(self, beings: BeingLookup) -> None:
        self._beings = beings

    def persona_of(self, being_id: BeingId) -> Persona:
        return self._beings.get(being_id).persona

    def persona_text_of(self, being_id: BeingId) -> str:
        return self.circumstances_of(being_id).persona_text

    def circumstances_of(self, being_id: BeingId) -> EpisodeWritingCircumstances:
        being = self._beings.get(being_id)
        return EpisodeWritingCircumstances(
            persona_text=persona_text_of(being), environment_name=being.current_environment_name()
        )


__all__ = ["CircumstancesOfBeings"]
