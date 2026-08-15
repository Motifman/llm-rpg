"""所持金を動かしうる経路が、1 つ残らず記録の包みを通っていることを保証する。

## なぜこの試験が要るか

`gold_after` / `gold_delta` / `gold_change_source` を出していたのは商人ツール
(`buy_item` / `sell_item`) **だけ**だった。板を通した売買は 7G 増えても所持金の
記録が 1 行も出ず、実 run (`market_town_v3_first`) の分析で台帳が組めなかった。

商人ツールだけが出していたのは、**先に作ったからで設計判断ではない**。同じ形の
漏れは、ツールを足すたびに何度でも起きる。しかも**漏れても例外は出ない** —
run が終わって「所持金の推移が引けない」で初めて気づく。

だから個別のツールを数え上げるのではなく、**dispatch に登録された全ハンドラが
包まれていること**を見る。新しいツールを足した人が何も知らなくても、この試験が
自動で対象にする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (
    WorldLlmWiring,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)


@pytest.fixture(scope="module")
def handlers():
    runtime = create_world_runtime(str(_SCENARIO))
    wiring = WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
    )
    return dict(wiring._tool_handlers)


class TestNoToolCanMoveGoldWithoutSayingSo:
    """dispatch に登録された全ツールが、所持金の変化を測る包みを通っている。"""

    def test_the_world_actually_registered_some_tools(self, handlers) -> None:
        """まず、見るべきハンドラが存在する (**空を全数一致と読まない**)。

        この対照が無いと、配線が丸ごと壊れて 0 件になったときに、下の
        全数検査が「全部通っている」と嘘をつく。
        """
        assert len(handlers) > 10

    def test_every_registered_handler_is_wrapped(self, handlers) -> None:
        """1 つ残らず包まれている。

        包み漏れがあると、そのツールで動いた gold は trace に残らず、
        **run が終わってから「所持金が引けない」でしか気づけない**。
        """
        unwrapped = sorted(
            name for name, handler in handlers.items()
            if not getattr(handler, "records_gold_change", False)
        )

        assert unwrapped == []

    def test_the_market_tools_are_among_them(self, handlers) -> None:
        """今回漏れていた市場ツールが、実際に対象に入っている。

        全数検査だけだと、市場ツールが**そもそも登録されていない**世界でも
        緑になる。塞いだ穴そのものを名指しで見る。
        """
        market = {
            name for name in handlers
            if name.startswith("spot_graph_market") or "market" in name
        }

        assert len(market) >= 5


class TestTheWrappingActuallyWatchesEveryone:
    """配線が、**その場の全員**を測る形になっている。"""

    def test_every_handler_is_given_the_roster(self, monkeypatch) -> None:
        """包むときに、全員の名簿が渡されている。

        名簿を渡し忘れると呼んだ人だけを測る形へ静かに戻り、**二者間の
        取引で相手側が記録から消える**。包み自体は付いたままなので、
        「包まれているか」の検査では気づけない。
        """
        from ai_rpg_world.application.llm.services.world_llm_turn import (
            tool_dispatch,
        )

        seen: list = []
        original = tool_dispatch.wrap_with_gold_change

        def _spy(handler, gold_reader, **kwargs):
            seen.append(kwargs.get("roster_reader"))
            return original(handler, gold_reader, **kwargs)

        monkeypatch.setattr(tool_dispatch, "wrap_with_gold_change", _spy)
        runtime = create_world_runtime(str(_SCENARIO))
        WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
        )

        assert seen, "ツールが 1 つも包まれていない"
        assert all(reader is not None for reader in seen)

    def test_the_roster_covers_the_whole_town(self) -> None:
        """名簿に、世界の全員が入っている (**正の対照**)。

        名簿が空でも上の検査は通る。空の名簿は「全員測る」と同じ形をして
        いて、実際には誰も測らない。
        """
        from ai_rpg_world.application.llm.services.world_llm_turn.gold_change_trace import (  # noqa: E501
            build_roster_reader,
        )

        runtime = create_world_runtime(str(_SCENARIO))

        roster = build_roster_reader(runtime._player_status_repo)()

        assert len(roster) == 5
