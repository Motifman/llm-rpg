from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception, DeliverPerceptionCommand
from ai_rpg_world.game_world.application.stimulus_translator import StimulusTranslator
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception import Stimulus
from ai_rpg_world.game_world.domain.perception.occurrences_in_commit import Occurrence, OccurrencesInCommit


@final
class DeliverPerceptionOfCommittedEvents:
    def __init__(self, scope: CommandScope, design: WorldDesign, deliver_perception: DeliverPerception) -> None:
        self._scope = scope
        self._design = design
        self._translator = StimulusTranslator()
        self._deliver_perception = deliver_perception

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        for occurrence in OccurrencesInCommit.split(events):
            command = self._scope.run(lambda session: self._command_for(occurrence, session.facts()))
            if command.carries_stimuli():
                self._deliver_perception(command)

    def _command_for(self, occurrence: Occurrence, facts: WorldFacts) -> DeliverPerceptionCommand:
        return DeliverPerceptionCommand(
            cause=occurrence.cause,
            from_actions=self._stimuli_of(occurrence.from_actions(), facts),
            from_states=self._stimuli_of(occurrence.from_states(), facts),
        )

    def _stimuli_of(self, events: tuple[DomainEvent, ...], facts: WorldFacts) -> tuple[Stimulus, ...]:
        return tuple(
            stimulus for event in events for stimulus in self._translator.stimuli_of(event, self._design, facts)
        )
