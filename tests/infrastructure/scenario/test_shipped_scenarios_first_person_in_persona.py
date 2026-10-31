"""同梱のシナリオで、players[].first_person と persona_prompt に書き足した一人称が食い違わないことを見張る (design_decisions D1469-3)。

行動を決める LLM には、まだ Persona から一人称が渡らない。人格の文を Persona から作るまで (#1339 / #1548)、
persona_prompt の「話し方:」の行に同じ一人称を書き足して伝える。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_FIRST_PERSON_IN_PROMPT = re.compile(r"一人称は「([^」]+)」")


def _players_with_first_person_or_mention() -> list[tuple[str, dict]]:
    found = []
    for path in sorted(_SCENARIOS.glob("*.json")):
        for player in json.loads(path.read_text(encoding="utf-8")).get("players", []):
            if "first_person" in player or _FIRST_PERSON_IN_PROMPT.search(player.get("persona_prompt") or ""):
                found.append((f"{path.stem}:{player['id']}", player))
    return found


_PLAYERS = _players_with_first_person_or_mention()


def test_every_mine_village_player_declares_a_first_person() -> None:
    """mine_village_v1 の 4 人は全員が一人称を書いている。1 人が欄と書き足しを同時に消しても、下の見張りから外れて気づけないため。"""
    declared = {label for label, player in _PLAYERS if "first_person" in player}

    assert {label for label in declared if label.startswith("mine_village_v1:")} == {
        "mine_village_v1:haru",
        "mine_village_v1:mio",
        "mine_village_v1:gen",
        "mine_village_v1:sayo",
    }


@pytest.mark.parametrize(("label", "player"), _PLAYERS, ids=[label for label, _ in _PLAYERS])
def test_persona_prompt_tells_the_same_first_person(label: str, player: dict) -> None:
    """first_person を書いたプレイヤーの persona_prompt は「一人称は「…」」で同じ一人称だけを書き、一人称を書いた persona_prompt は first_person も持つ。"""
    mentioned = _FIRST_PERSON_IN_PROMPT.findall(player.get("persona_prompt") or "")

    assert mentioned == [player.get("first_person")]
