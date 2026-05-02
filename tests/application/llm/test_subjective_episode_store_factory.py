"""subjective_episode_store_factory の単体テスト。"""

import pytest

from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.wiring.subjective_episode_store_factory import (
    ENV_SUBJECTIVE_EPISODE_DB_PATH,
    create_subjective_episode_store_for_wiring,
)
from ai_rpg_world.infrastructure.llm.sqlite_subjective_episode_store import (
    SqliteSubjectiveEpisodeStore,
)


def test_factory_explicit_instance_wins(tmp_path):
    mem = InMemorySubjectiveEpisodeStore()
    got = create_subjective_episode_store_for_wiring(
        subjective_episode_store=mem,
        sqlite_path=str(tmp_path / "x.db"),
        environ={ENV_SUBJECTIVE_EPISODE_DB_PATH: str(tmp_path / "y.db")},
    )
    assert got is mem


def test_factory_sqlite_path_over_env(tmp_path):
    db = tmp_path / "a.db"
    got = create_subjective_episode_store_for_wiring(
        sqlite_path=str(db),
        environ={ENV_SUBJECTIVE_EPISODE_DB_PATH: str(tmp_path / "b.db")},
    )
    assert isinstance(got, SqliteSubjectiveEpisodeStore)
    assert got._db_path == str(db)


def test_factory_rejects_bad_explicit_type():
    with pytest.raises(TypeError, match="ISubjectiveEpisodeStore"):
        create_subjective_episode_store_for_wiring(subjective_episode_store=object())  # type: ignore[arg-type]


def test_factory_in_memory_when_empty(tmp_path):
    got = create_subjective_episode_store_for_wiring(
        environ={ENV_SUBJECTIVE_EPISODE_DB_PATH: "  "},
    )
    assert isinstance(got, InMemorySubjectiveEpisodeStore)

