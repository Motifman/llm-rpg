"""隣から漏れ聞こえる言葉が、全文ではなく断片であることを保証する。

## なぜこの試験が要るか

聞こえ方は 3 段階ある。ところが真ん中が、近いほうと同じだった。

| | いままで | 妥当か |
|---|---|---|
| CLEAR (同じ場所) | 全文 | ○ |
| **MUFFLED (隣の部屋)** | **全文** | **× 遠いのに全部聞こえる** |
| FAINT (さらに遠い) | 内容を伏せる | ○ |

**「遠くの声が聞こえる」と言いながら、完全な書き起こしを渡していた。** 段階が
3 つあるのに、実質 2 つしか機能していない。

隣の部屋の会話を一言一句知っている世界では、**移動して話を聞きに行く理由が
薄くなる**。これは節約の話ではなく、世界の壊れ方の話である (v3.1 の実 run では
1 手番あたり 1,140 文字が、この全文だった)。
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

_MODULE = "ai_rpg_world.application.observation.services.formatters.player_formatter"

_LONG = "レナ、さっき薬草摘んだんだってな。この辺で長くやってるのか？俺はノラって言うんだ。"


@pytest.fixture
def formatter() -> Any:
    return importlib.import_module(_MODULE)


class TestOnlyAFragmentCarriesOverTheDistance:
    """遠くの声は、聞き取れたぶんだけになる。"""

    def test_a_long_speech_is_cut_short(self, formatter) -> None:
        """長い発話は、先頭だけを残して切られる。"""
        fragment = formatter._overheard_fragment(_LONG)

        assert len(fragment) < len(_LONG)
        assert fragment.endswith("…")

    def test_the_beginning_survives(self, formatter) -> None:
        """切っても、話の出だしは残る。

        **誰が何の話をしているかは分かる**長さにする。全部伏せると
        FAINT (さらに遠い段階) と区別がつかなくなる。
        """
        fragment = formatter._overheard_fragment(_LONG)

        assert fragment.startswith("レナ、さっき薬草")

    def test_a_short_speech_is_left_alone(self, formatter) -> None:
        """短い発話はそのまま (**正の対照**)。

        何でも切ると、「切られた」ことが情報にならない。
        """
        assert formatter._overheard_fragment("おーい") == "おーい"

    def test_nothing_becomes_nothing(self, formatter) -> None:
        """空の発話で落ちない。"""
        assert formatter._overheard_fragment("") == ""


class TestTheThreeDistancesAreActuallyDifferent:
    """3 つの段階が、それぞれ違うものを返す。"""

    def test_the_fragment_is_shorter_than_the_full_text(self, formatter) -> None:
        """中間の段階が、近い段階より短い。

        ここが同じだと、**段階が 3 つあるのに 2 つしか意味を持たない**。
        """
        full = _LONG
        fragment = formatter._overheard_fragment(_LONG)

        assert 0 < len(fragment) < len(full)


class TestTheFragmentReachesTheListener:
    """断片が、実際に聞き手の観測へ届く。

    **補助関数が正しくても、繋がっていなければ何も変わらない。** 今日の型の
    ひとつなので、実経路でも見る。
    """

    def _muffled_output(self, content: str) -> Any:
        from ai_rpg_world.application.observation.services.observation_formatter import (  # noqa: E501
            ObservationFormatter,
        )
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
        from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (  # noqa: E501
            InMemorySpotGraphRepository,
        )
        from tests.application.observation.test_spot_graph_speech_observation import (
            _build_two_spot_graph,
        )

        formatter = ObservationFormatter(
            spot_graph_repository=InMemorySpotGraphRepository(
                _build_two_spot_graph(perm=0.5)
            )
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content=content,
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        return formatter.format(event, PlayerId(2))

    def test_the_listener_hears_only_the_fragment(self) -> None:
        """隣の部屋の聞き手には、断片だけが届く。"""
        out = self._muffled_output(_LONG)

        assert out is not None
        assert "遠くの声" in out.prose
        assert _LONG not in out.prose
        assert "…" in out.prose

    def test_the_structured_side_agrees_with_what_was_heard(self) -> None:
        """構造化側にも全文を残さない。

        prose だけ切って構造化側に全文を置くと、**記憶や分析にだけ完全な
        書き起こしが残り**、どちらが本当に聞こえたのか分からなくなる。
        """
        out = self._muffled_output(_LONG)

        assert out.structured.get("content") != _LONG
        assert out.structured.get("sound_clarity") == "MUFFLED"
