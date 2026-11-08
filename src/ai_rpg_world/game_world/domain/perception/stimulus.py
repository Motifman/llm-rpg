from __future__ import annotations

from ai_rpg_world.game_world.domain.perception.announcement_stimulus import AnnouncementStimulus
from ai_rpg_world.game_world.domain.perception.bodily_stimulus import BodilyStimulus
from ai_rpg_world.game_world.domain.perception.sight_stimulus import SightStimulus
from ai_rpg_world.game_world.domain.perception.sound_stimulus import SoundStimulus

Stimulus = SightStimulus | SoundStimulus | BodilyStimulus | AnnouncementStimulus
