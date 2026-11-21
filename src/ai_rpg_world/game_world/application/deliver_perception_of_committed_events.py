from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception, DeliverPerceptionCommand
from ai_rpg_world.game_world.application.stimulus_translator import StimulusTranslator
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception import Stimulus
from ai_rpg_world.game_world.domain.perception.occurrences_in_commit import OccurrencesInCommit


@final
class DeliverPerceptionOfCommittedEvents:
    def __init__(self, design: WorldDesign, deliver_perception: DeliverPerception) -> None:
        self._design = design
        self._translator = StimulusTranslator()
        self._deliver_perception = deliver_perception

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        for occurrence in OccurrencesInCommit.split(events):
            command = DeliverPerceptionCommand(
                cause=occurrence.cause,
                from_actions=self._stimuli_of(occurrence.from_actions()),
                from_states=self._stimuli_of(occurrence.from_states()),
            )
            if command.carries_stimuli():
                self._deliver_perception(command)

    def _stimuli_of(self, events: tuple[DomainEvent, ...]) -> tuple[Stimulus, ...]:
        return tuple(stimulus for event in events for stimulus in self._translator.stimuli_of(event, self._design))
