from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
    PromptDatasetCaptureSink,
    reconstruct_request,
)
from ai_rpg_world.being.application.choose_action import (
    ActionChoosingReply,
    ChooseAction,
    ChooseActionCommand,
    ToolCallReply,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode_writer import EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.infrastructure.scripted_backstory_writer import ScriptedBackstoryWriter
from ai_rpg_world.being.infrastructure.scripted_episode_writer import ScriptedEpisodeWriter
from ai_rpg_world.experiment.infrastructure.game_world_play import GameWorldPlay, GameWorldWriters
from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings
from ai_rpg_world.experiment.infrastructure.game_world_run import game_world_writers
from ai_rpg_world.experiment.infrastructure.llm_call_capture import (
    CountedPromptSink,
    LabeledChooseAction,
    LabeledEpisodeWriter,
    LlmCallCapture,
    LlmCallLabel,
    PromptCapture,
)
from ai_rpg_world.experiment.infrastructure.murmuring_action_choosing import MurmuringActionChoosing
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.infrastructure.llm import litellm_client

_MINE_VILLAGE_V2 = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_NAMED = re.compile(r"あなたは(.+?)、")


def _sink(out: Path) -> CountedPromptSink:
    return CountedPromptSink(
        PromptDatasetCaptureSink(run_dir=out, run_id="test", run_metadata={}, failure_policy="fail")
    )


def _calls(out: Path) -> list[dict[str, Any]]:
    dataset = out / "prompt_dataset"
    prompts = {
        r["system_prompt_id"]: r for r in map(json.loads, (dataset / "system_prompts.jsonl").read_text().splitlines())
    }
    toolsets = {r["toolset_id"]: r for r in map(json.loads, (dataset / "toolsets.jsonl").read_text().splitlines())}
    calls = []
    for row in map(json.loads, (dataset / "calls.jsonl").read_text().splitlines()):
        row["restored"] = reconstruct_request(row, prompts, toolsets)
        calls.append(row)
    return calls


def _named_in(call: dict[str, Any]) -> str:
    found = _NAMED.search(call["restored"]["messages"][0]["content"])
    assert found is not None
    return found.group(1)


def _play(writers: GameWorldWriters, capture: LlmCallCapture, *, round_limit: int) -> GameWorldPlay:
    return GameWorldPlay(
        scenario_path=_MINE_VILLAGE_V2,
        scenario=load_scenario(_MINE_VILLAGE_V2),
        scenario_hash=hashlib.sha256(_MINE_VILLAGE_V2.read_bytes()).hexdigest(),
        settings=GameWorldPlaySettings(),
        writers=writers,
        round_limit=round_limit,
        capture=capture,
    )


def _stub_writers(choosing: Any) -> GameWorldWriters:
    return GameWorldWriters(
        action_choosing=choosing, episode_writer=ScriptedEpisodeWriter(), backstory_writer=ScriptedBackstoryWriter()
    )


class _SwappedReplies(MurmuringActionChoosing):
    """ゲンの返事は、ミオが返したあとまで返さない。並べて呼ばれた 2 人の返事の順を、呼んだ順と入れ替える。"""

    def __init__(self) -> None:
        super().__init__()
        self._mio_returned = threading.Event()
        self.timed_out = False

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        name = _NAMED.search(messages[0]["content"]).group(1)  # type: ignore[union-attr]
        if name == "ゲン" and not self._mio_returned.wait(timeout=5):
            self.timed_out = True
        reply = super().choose_action(messages, tools, reasoning_off=reasoning_off)
        if name == "ミオ":
            self._mio_returned.set()
        return reply


class TestLlmCallsInThePromptDataset:
    """新しい世界の run が、LLM の呼び出しごとに、誰の・いつの・何の呼び出しかと全文を prompt_dataset に 1 行ずつ残すことを保証する。"""

    def test_one_row_per_finished_turn_with_the_full_request_and_reply(self, tmp_path: Path) -> None:
        """スタブで 2 巡り回すと、終えたターンと同じ 8 行が残り、1 行からシステムとユーザーのメッセージの全文、ツールの定義、選んだツールが読める。"""
        sink = _sink(tmp_path)
        capture = LlmCallCapture()

        result = _play(_stub_writers(MurmuringActionChoosing()), capture, round_limit=2).play(prompts=sink, run_id="t")

        calls = _calls(tmp_path)
        assert len(calls) == result.finished_turns == 8 == sink.recorded
        gens = next(c for c in calls if c["character_name"] == "ゲン")
        assert gens["phase"] == "choose_action" and gens["world_tick"] == 0
        assert [m["role"] for m in gens["restored"]["messages"]] == ["system", "user"]
        assert "【選べる操作】" in gens["restored"]["messages"][1]["content"]
        assert any(t["function"]["name"] == "speak" for t in gens["restored"]["tools"])
        assert gens["output"]["tool"] == "speak"

    def test_rows_name_the_right_person_when_replies_come_back_out_of_order(self, tmp_path: Path) -> None:
        """4 人が同時に考え、ゲンの返事がミオより後に返っても、どの行の人も、その行のプロンプトの人柄の名前と一致する。"""
        completion = _SwappedReplies()

        _play(_stub_writers(completion), LlmCallCapture(), round_limit=1).play(prompts=_sink(tmp_path), run_id="t")

        assert not completion.timed_out
        calls = _calls(tmp_path)
        assert len(calls) == 4
        assert all(c["character_name"] == _named_in(c) for c in calls)

    def test_failed_call_leaves_a_row_with_the_error(self, tmp_path: Path) -> None:
        """ゲンの呼び出しが例外で落ちても、ゲンの行は残り、落ちた理由が入る。"""

        class _GenFails(MurmuringActionChoosing):
            def choose_action(
                self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
            ) -> ActionChoosingReply:
                if "あなたはゲン、" in messages[0]["content"]:
                    raise TimeoutError("no reply in 95 seconds")
                return super().choose_action(messages, tools, reasoning_off=reasoning_off)

        _play(_stub_writers(_GenFails()), LlmCallCapture(), round_limit=1).play(prompts=_sink(tmp_path), run_id="t")

        [gens] = [c for c in _calls(tmp_path) if c["character_name"] == "ゲン"]
        assert "no reply in 95 seconds" in json.dumps(gens["response"]["error"], ensure_ascii=False)

    def test_failing_to_write_keeps_the_play_and_counts_it(self, tmp_path: Path) -> None:
        """prompt_dataset に書けなくても遊びは最後まで進み、書けなかった数が残る。"""

        class _Broken(PromptDatasetCaptureSink):
            def record_call(self, **kwargs: Any) -> None:
                raise OSError("disk is full")

        sink = CountedPromptSink(_Broken(run_dir=tmp_path, run_id="t", run_metadata={}, failure_policy="fail"))

        result = _play(_stub_writers(MurmuringActionChoosing()), LlmCallCapture(), round_limit=1).play(
            prompts=sink, run_id="t"
        )

        assert (result.finished_turns, result.failed_choices) == (4, ())
        assert (result.llm_calls_recorded, result.llm_calls_not_recorded) == (0, 4)


def _tool_response(*_: Any, **kwargs: Any) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_tokens=100, completion_tokens=10, prompt_tokens_details=SimpleNamespace(cached_tokens=0)
    )
    if "tools" in kwargs:
        call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(
                name="speak", arguments=json.dumps({"reach": "ふつうの声で話す", "content": "ふむ"})
            ),
        )
        message = SimpleNamespace(content=None, tool_calls=[call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")], usage=usage)
    message = SimpleNamespace(content=json.dumps({"backstory": "坑道で話した。", "episodes": []}), tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=usage)


class TestLiteLlmCallsInThePromptDataset:
    """LiteLLM で組んだ新しい世界が、行動を選ぶ呼び出しと書き起こしの呼び出しを、生の返事と誰のものかつきで残すことを保証する。実 endpoint は叩かない。"""

    def test_writing_calls_are_kept_with_whose_memory_they_are(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """20 巡り回すと、いきさつの書き起こしの行が、誰の記憶かの名前つきで残り、その行のプロンプトの人柄と一致する。行動を選ぶ行には生の返事が入る。"""
        monkeypatch.setattr(litellm_client, "_load_dotenv_if_available", lambda: None)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
        monkeypatch.setattr(litellm_client.litellm, "completion", _tool_response)
        capture = LlmCallCapture()
        settings = GameWorldPlaySettings.from_runtime_config(
            {"LLM_CLIENT": "litellm", "LLM_MODEL": "openrouter/deepseek/deepseek-v4.1-flash"}
        )

        _play(game_world_writers(settings, capture), capture, round_limit=20).play(prompts=_sink(tmp_path), run_id="t")

        calls = _calls(tmp_path)
        writing = [c for c in calls if c["phase"] == "backstory_writing"]
        assert writing
        assert all(
            c["character_name"] in c["restored"]["messages"][0]["content"] + c["restored"]["messages"][-1]["content"]
            for c in writing
        )
        choosing = next(c for c in calls if c["phase"] == "choose_action")
        assert choosing["response"]["raw"] is not None


class _WritingAfterTheOther(EpisodeWriter):
    """2 人の書き起こしを裏のスレッドで同時に走らせ、互いが名札を付けたあとで呼び出しの文脈を作る。"""

    def __init__(self, capture: LlmCallCapture, both_labeled: threading.Barrier) -> None:
        self._capture = capture
        self._both_labeled = both_labeled
        self.captured: dict[str, PromptCapture | None] = {}

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        self._both_labeled.wait(timeout=5)
        self.captured[persona.name] = self._capture.capture()
        return EpisodeContents(contents=())


class TestLabelsOfWritingOnThreads:
    """書き起こしを裏のスレッドで同時に走らせても、各呼び出しの文脈が、そのスレッドで書いている人のものになることを保証する。"""

    def test_two_writers_at_once_get_their_own_labels(self, tmp_path: Path) -> None:
        """ゲンとサヨの書き起こしが同時に名札を付けても、ゲンの呼び出しはゲン、サヨの呼び出しはサヨの文脈になる。"""
        capture = LlmCallCapture()
        capture.attach(_sink(tmp_path), "t")
        inner = _WritingAfterTheOther(capture, threading.Barrier(2))
        people = {"ゲン": PersonId("gen"), "サヨ": PersonId("sayo")}

        def label_for(persona: Persona, purpose: str) -> LlmCallLabel:
            person = people[persona.name]
            return LlmCallLabel(person, persona.name, 1, BeingId(person.value), 5, purpose)

        writer = LabeledEpisodeWriter(inner, label_for=label_for)
        threads = [
            threading.Thread(
                target=writer.write,
                kwargs={"persona": Persona(name=name, speech="常体"), "persona_text": "", "events_text": "x"},
            )
            for name in people
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        assert {name: c.context.character_name for name, c in inner.captured.items() if c is not None} == {
            "ゲン": "ゲン",
            "サヨ": "サヨ",
        }


class _ThinkingAfterTheOther:
    """2 人の考える段を同時に走らせ、互いが名札を付けたあとで呼び出しの文脈を作る。"""

    def __init__(self, capture: LlmCallCapture, both_labeled: threading.Barrier) -> None:
        self._capture = capture
        self._both_labeled = both_labeled
        self.captured: dict[str, PromptCapture | None] = {}

    def prompt(self, command: Any) -> Any:
        return SimpleNamespace(being=command.being_id)

    def think(self, prompt: Any) -> Any:
        self._both_labeled.wait(timeout=5)
        self.captured[prompt.being.value] = self._capture.capture()
        return prompt


class TestLabelsOfThinkingOnThreads:
    """考える段を worker で同時に走らせても、各呼び出しの文脈が、そのスレッドで考えている人のものになることを保証する。"""

    def test_two_thinkers_at_once_get_their_own_labels(self, tmp_path: Path) -> None:
        """ゲンとミオが同時に名札を付けてから LLM を呼んでも、ゲンの呼び出しはゲン、ミオの呼び出しはミオの文脈になる。"""
        capture = LlmCallCapture()
        capture.attach(_sink(tmp_path), "t")
        inner = _ThinkingAfterTheOther(capture, threading.Barrier(2))
        names = {"gen": "ゲン", "mio": "ミオ"}

        def label_for(being_id: BeingId, purpose: str) -> LlmCallLabel:
            return LlmCallLabel(PersonId(being_id.value), names[being_id.value], 1, being_id, 0, purpose)

        choose = LabeledChooseAction(cast(ChooseAction, inner), label_for=label_for)
        prompts = [choose.prompt(cast(ChooseActionCommand, SimpleNamespace(being_id=BeingId(b)))) for b in names]
        threads = [threading.Thread(target=choose.think, args=(p,)) for p in prompts]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        assert {b: c.context.character_name for b, c in inner.captured.items() if c is not None} == names
