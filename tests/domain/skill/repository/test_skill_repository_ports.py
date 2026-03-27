from __future__ import annotations

import pytest

from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
    SkillLoadoutRepository,
    SkillSpecWriter,
)


def test_skill_loadout_repository_is_abstract() -> None:
    with pytest.raises(TypeError):
        SkillLoadoutRepository()  # type: ignore[abstract]


def test_skill_deck_progress_repository_is_abstract() -> None:
    with pytest.raises(TypeError):
        SkillDeckProgressRepository()  # type: ignore[abstract]


def test_skill_spec_writer_is_abstract() -> None:
    with pytest.raises(TypeError):
        SkillSpecWriter()  # type: ignore[abstract]
