from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any, cast

from ai_rpg_world.application.llm.services.prompt_dataset_capture import PromptDatasetCaptureSink
from ai_rpg_world.being.application.choose_action import ActionChoosingReply, ToolCallReply
from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from ai_rpg_world.experiment.infrastructure.game_world_play import GameWorldPlay, GameWorldWriters
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings
from ai_rpg_world.experiment.infrastructure.murmuring_action_choosing import MurmuringActionChoosing
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.play_session.application.play_rounds import RoundLimitReached

_MINE_VILLAGE_V2 = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"


class _RecordingMurmurs(MurmuringActionChoosing):
    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []
        self._prompts_lock = threading.Lock()

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        with self._prompts_lock:
            self.prompts.append(messages[-1]["content"])
        return super().choose_action(messages, tools, reasoning_off=reasoning_off)


def _play(completion: MurmuringActionChoosing, *, round_limit: int) -> GameWorldPlay:
    return GameWorldPlay(
        scenario_path=_MINE_VILLAGE_V2,
        scenario=load_scenario(_MINE_VILLAGE_V2),
        scenario_hash=hashlib.sha256(_MINE_VILLAGE_V2.read_bytes()).hexdigest(),
        settings=GameWorldPlaySettings(),
        writers=GameWorldWriters(
            action_choosing=completion,
            episode_writer=ScriptedEpisodeWriter(),
            backstory_writer=ScriptedBackstoryWriter(),
        ),
        round_limit=round_limit,
    )


class TestGameWorldPlay:
    """GameWorldPlay が、本番の部品で廃坑の山村 v2 を組み、世界で起きたことを Being の次の場面まで届けることを保証する。"""

    def test_what_someone_said_reaches_the_others_next_prompt(self) -> None:
        """1 巡り目に全員がふつうの声で「ふむ」と言うと、2 巡り目のだれかのプロンプトの【直近の出来事】に、ほかの人の「ふむ」が届いている。"""
        completion = _RecordingMurmurs()

        result = _play(completion, round_limit=2).play()

        assert isinstance(result.stopped, RoundLimitReached)
        second_round = completion.prompts[4:]
        assert any("が「ふむ」と言った。" in prompt for prompt in second_round)

    def test_last_tick_and_turns_are_counted_after_the_play(self) -> None:
        """2 巡り回すと、最後の tick は 2 で、4 人ぶん 8 ターンを終えたと数える。"""
        result = _play(MurmuringActionChoosing(), round_limit=2).play()

        assert (result.last_tick.value, result.finished_turns) == (2, 8)


class _Kept:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None:
        self.records.append((kind, payload))


class _GoingWhereNoOneCan(MurmuringActionChoosing):
    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        return ActionChoosingReply(
            tool_call=ToolCallReply(tool_name="travel_to", arguments={"destination": "北の坑道"}, call_id="go_north")
        )


class TestBeingTurnsInTheTrace:
    """GameWorldPlay が、LLM とのやりとりと行為の結果を、誰のものかが分かる形で trace に書くことを保証する。"""

    def test_refused_action_keeps_its_reason_with_whose_attempt_it_was(self) -> None:
        """全員が候補に無い「北の坑道」へ行こうとすると、行為の結果の行に、断られた印と「北の坑道」を含む理由が、試みの call_id と一緒に人ごとに残る。"""
        kept = _Kept()

        _play(_GoingWhereNoOneCan(), round_limit=1).play(kept)

        results = [p for kind, p in kept.records if kind == "game_world.action_result"]
        assert {p["person"]["name"] for p in results} == {"ハル", "ミオ", "ゲン", "サヨ"}
        assert all(p["route"]["succeeded"] is False and p["route"]["call_id"] == "go_north" for p in results)
        assert all("北の坑道" in str(p["body"]) for p in results)

    def test_choice_names_the_person_and_the_chosen_move(self) -> None:
        """1 巡り回すと、選んだ行動の行が 4 人ぶん出て、場面の現在地・候補表・選んだ行動と、プロンプトの sha256 が残る。"""
        kept = _Kept()

        _play(MurmuringActionChoosing(), round_limit=1).play(kept)

        choices = [p for kind, p in kept.records if kind == "game_world.choice"]
        assert len(choices) == 4
        gens = next(p for p in choices if p["person"]["name"] == "ゲン")
        assert gens["move"] == {"tool": "speak", "arguments": {"reach": "ふつうの声で話す", "content": "ふむ"}}
        assert gens["scene"]["here"]["place"] == "南の横坑口"
        assert "travel_to.destination" in gens["candidate_table"]
        assert len(gens["prompt_sha256"]) == 64

    def test_failing_to_write_the_prompt_keeps_the_turn(self) -> None:
        """プロンプトの全文を書き出せなくても、そのターンは選べなかったターンにならず、書けなかった数が残る。"""

        class _BrokenPrompts:
            def record_call(self, **_: object) -> None:
                raise OSError("disk is full")

        result = _play(MurmuringActionChoosing(), round_limit=1).play(
            _Kept(), prompts=cast(PromptDatasetCaptureSink, _BrokenPrompts())
        )

        assert result.failed_choices == ()
        assert (result.finished_turns, result.trace_failures) == (4, 4)
