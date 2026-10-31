"""CurrentWorkingMemory が Being の持ち物を保存先から集めて作業記憶を組み、ターンをまたいで
末尾に足す区画の途中を書き換えないことを保証する (design_decisions D1630-2)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.application.current_working_memory import CurrentWorkingMemory
from ai_rpg_world.being.application.working_memory_text import message_text, section_text, system_prompt_text
from ai_rpg_world.being.contract import (
    UNKNOWN,
    Description,
    Observation,
    ObservedTime,
    Orientation,
    Scene,
    SeenOrHeard,
)
from ai_rpg_world.being.domain.acquaintance import Acquaintance
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.working_memory import Closing, Steadiness, WorkingMemory
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)

HAL = BeingId("being_hal")
VILLAGE = BeingAttachment(environment_id="mine_village_v1#1", environment_name="廃坑の山村")


class _Beings:
    def __init__(self, *beings: Being) -> None:
        self._beings = {b.being_id: b for b in beings}

    def find_by_id(self, being_id: BeingId) -> Being | None:
        return self._beings.get(being_id)


def _observation(body: str) -> Observation:
    return Observation(
        body=body,
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


@pytest.fixture
def stores() -> dict[str, object]:
    acquaintances = InMemoryAcquaintanceRepository()
    acquaintances.record_introduction(HAL, environment_name="廃坑の山村", name="ミオ", turn=0, relation_note=None)
    acquaintances.record_introduction(HAL, environment_name="遭難の島", name="リオ", turn=0, relation_note=None)
    return {
        "beings": _Beings(Being(being_id=HAL, persona=Persona(name="ハル"), attachment=VILLAGE)),
        "short_term_memories": InMemoryShortTermMemoryRepository(),
        "acquaintances": acquaintances,
        "episodes": InMemoryEpisodeRepository(),
        "memo_books": InMemoryMemoBookRepository(),
    }


def _of(stores: dict[str, object], being_id: BeingId = HAL) -> WorkingMemory:
    current = CurrentWorkingMemory(episode_index_limit=5, **stores)  # type: ignore[arg-type]
    return current.of(
        being_id,
        orientation=Orientation([Description(heading="ペルソナ", text="あなたはハル。")]),
        conduct="【行動ルール】\n- 1 回に 1 つ",
        imposed_goal="外へ出る",
        scene=Scene([Description(heading="現在地と周囲", text="北の竪坑口")]),
        closing=Closing(instruction="行動を 1 つ選んでください。"),
    )


class TestGathering:
    """Being の持ち物から区画の本文を集めることを保証する。"""

    def test_known_people_are_those_of_the_current_environment(self, stores: dict[str, object]) -> None:
        """知っている人は、Being が今いる環境で知った人だけになる。"""
        known = next(s for s in _of(stores).message if s.heading == "知っている人")

        assert known.lines == ("- ミオ",)

    def test_events_in_short_term_memory_appear_in_recent_events(self, stores: dict[str, object]) -> None:
        """短期記憶に積んだ出来事が【直近の出来事】に出る。"""
        memory = stores["short_term_memories"].get(HAL)  # type: ignore[attr-defined]
        memory.perceive(_observation("風が吹いた"), current_turn=1)
        stores["short_term_memories"].save(memory)  # type: ignore[attr-defined]

        assert "風が吹いた" in message_text(_of(stores))

    def test_empty_index_and_memo_still_appear(self, stores: dict[str, object]) -> None:
        """エピソードもメモも無くても、目次とメモの区画は空と分かる文で出る。"""
        headings = [s.heading for s in _of(stores).message]

        assert {"思い出せる出来事", "メモ"} <= set(headings)

    def test_being_outside_any_environment_raises(self, stores: dict[str, object]) -> None:
        """どの環境にも入っていない Being の作業記憶は組めず、LookupError を投げる。"""
        stores["beings"] = _Beings(Being(being_id=HAL, persona=Persona(name="ハル")))

        with pytest.raises(LookupError):
            _of(stores)


class TestAcrossTurns:
    """ターンをまたいで、前のターンの文が次のターンの文の先頭にそのまま残ることを保証する (不変条件 2)。

    いきさつが届くターンは見張りの対象外。いきさつは新しい順に並び、届いたときに直近の出来事の
    古い分も外れるので、途中が変わるのが正しい。
    """

    def test_new_acquaintance_keeps_everything_up_to_the_known_people(self, stores: dict[str, object]) -> None:
        """知っている人が 1 人増えても、システムプロンプトは同じで、メッセージは前のターンの【知っている人】までの文で始まる。"""
        before = _of(stores)
        stores["acquaintances"].record_introduction(  # type: ignore[attr-defined]
            HAL, environment_name="廃坑の山村", name="ハギ", turn=1, relation_note=None
        )

        after = _of(stores)

        up_to_known = []
        for section in before.message:
            up_to_known.append(section_text(section))
            if section.heading == "知っている人":
                break
        assert system_prompt_text(after) == system_prompt_text(before)
        assert message_text(after).startswith("\n\n".join(up_to_known))
        assert "- ハギ" in message_text(after)

    def test_new_event_keeps_everything_up_to_recent_events(self, stores: dict[str, object]) -> None:
        """出来事が 1 つ増えても、システムプロンプトは同じで、メッセージは直近の出来事までの前のターンの文で始まる。"""
        repository = stores["short_term_memories"]
        memory = repository.get(HAL)  # type: ignore[attr-defined]
        memory.perceive(_observation("風が吹いた"), current_turn=1)
        repository.save(memory)  # type: ignore[attr-defined]
        before = _of(stores)
        memory = repository.get(HAL)  # type: ignore[attr-defined]
        memory.perceive(_observation("扉が開いた"), current_turn=2)
        repository.save(memory)  # type: ignore[attr-defined]

        after = _of(stores)

        growing = "\n\n".join(section_text(s) for s in before.message if s.steadiness <= Steadiness.GROWING)
        assert system_prompt_text(after) == system_prompt_text(before)
        assert message_text(after).startswith(growing)
        assert message_text(after) != message_text(before)
