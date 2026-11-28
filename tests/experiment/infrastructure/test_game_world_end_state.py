from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from ai_rpg_world.experiment.infrastructure.game_world_play import GameWorldPlay, GameWorldWriters
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings
from ai_rpg_world.experiment.infrastructure.murmuring_action_choosing import MurmuringActionChoosing
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore

_MINE_VILLAGE_V2 = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_HASH = hashlib.sha256(_MINE_VILLAGE_V2.read_bytes()).hexdigest()


def _play(out: Path, choosing: Any, *, round_limit: int) -> GameWorldPlay:
    return GameWorldPlay(
        scenario_path=_MINE_VILLAGE_V2,
        scenario=load_scenario(_MINE_VILLAGE_V2),
        scenario_hash=_HASH,
        settings=GameWorldPlaySettings(),
        writers=GameWorldWriters(
            action_choosing=choosing, episode_writer=ScriptedEpisodeWriter(), backstory_writer=ScriptedBackstoryWriter()
        ),
        round_limit=round_limit,
        world_path=out / "world.sqlite",
        beings_directory=out / "beings",
    )


def _reopened_tick(out: Path) -> int:
    store = SqliteWorldStore.open(
        out / "world.sqlite",
        scenario_hash=_HASH,
        design=load_scenario(_MINE_VILLAGE_V2).design,
        random=SeedableRandomSource(0),
    )
    try:
        return CommandScope(store, CommittedEventsDistributor()).run(lambda session: session.facts().now().value)
    finally:
        store.close()


class TestEndStateOfTheGameWorld:
    """GameWorldPlay が、run の終わりの世界を SQLite のファイルに、各 Being の人柄と記憶を 1 人 1 ファイルに残すことを保証する。"""

    def test_world_file_can_be_reopened_at_the_last_tick(self, tmp_path: Path) -> None:
        """3 巡り回したあと、OUT/world.sqlite を開き直すと、世界の時刻は 3 で、ゲンの居場所が読める。"""
        _play(tmp_path, MurmuringActionChoosing(), round_limit=3).play()

        store = SqliteWorldStore.open(
            tmp_path / "world.sqlite",
            scenario_hash=_HASH,
            design=load_scenario(_MINE_VILLAGE_V2).design,
            random=SeedableRandomSource(0),
        )
        try:
            now, where = CommandScope(store, CommittedEventsDistributor()).run(
                lambda session: (
                    session.facts().now().value,
                    session.aggregates().whereabouts().spot_of(PersonBody(PersonId("gen"))),
                )
            )
        finally:
            store.close()
        assert now == 3
        assert where is not None

    def test_each_being_leaves_a_file_with_its_persona_and_memory(self, tmp_path: Path) -> None:
        """25 巡り回したあと、4 人それぞれのファイルが残り、ゲンのファイルから人柄の名前、短期記憶、エピソードと目次が読める。"""
        result = _play(tmp_path, MurmuringActionChoosing(), round_limit=25).play()

        assert sorted(p.name for p in result.being_memory_files) == ["gen.json", "haru.json", "mio.json", "sayo.json"]
        gen = json.loads((tmp_path / "beings" / "gen.json").read_text(encoding="utf-8"))
        assert gen["person"] == {"person_id": "gen", "name": "ゲン"}
        assert gen["being"]["persona"]["name"] == "ゲン"
        assert gen["memory"]["being_short_term_memory"]
        [first, *_] = gen["memory"]["being_episodes"]
        assert first["index"]["summary"]

    def test_play_that_raised_still_leaves_both_files(self, tmp_path: Path) -> None:
        """5 巡り回したあと、Being を世界から離すところで例外が出て遊びが止まっても、5 tick の世界の world.sqlite と 4 人の記憶のファイルが残る。"""
        play = _play(tmp_path, MurmuringActionChoosing(), round_limit=5)

        def leaving_fails(command: object) -> None:
            raise RuntimeError("leaving failed")

        play._end_play = leaving_fails  # type: ignore[assignment,method-assign]

        with pytest.raises(RuntimeError, match="leaving failed"):
            play.play()

        assert _reopened_tick(tmp_path) == 5
        assert sorted(p.name for p in (tmp_path / "beings").iterdir()) == [
            "gen.json",
            "haru.json",
            "mio.json",
            "sayo.json",
        ]
