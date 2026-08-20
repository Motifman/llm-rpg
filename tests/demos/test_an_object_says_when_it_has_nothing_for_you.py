"""職能が合わない物体が、操作の代わりに「扱えない」と告げることを保証する。

## なぜこの試験が要るか

実 run の `INTERACTION_ACTION_NOT_FOUND` 5 件 (失敗の 50%) は、**全件が同じ形**
だった。職能が合わないと操作の一覧が**角括弧ごと消える**。

    職能が合う:   "石窯" — … [パンを焼く → "bake_bread"]
    職能が合わない: "石窯" — 熾火を抱えた石窯。麦束ひとつから…

ところが system prompt は「各オブジェクトに表示された操作の中から選ぶこと」と
指示している。**表示が 1 つも無いのに「表示から選べ」と言われた**エージェントは、
`examine` のような汎用動詞を発明する (5 件中 3 件がそれ)。

決定的なのは、**時間で戻らないことは既に注記されている**こと。

    "薬草の茂み" (今は採れない・時間を置けば戻る) — …

**時間ゲートは注記されるのに、職能ゲートは注記されない。** この非対称だけが原因
だった。

## 理由を断定しない

操作が落ちる理由は職能とは限らない。世界の状態でも落ちるし、**存在層 (幽霊など)
でも落ちる**。存在層が理由のときに注記を出すと「生者にだけ見える操作がある」ことを
漏らすので、**そのときは黙る**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)

#: 焼き手 (石窯を扱える) と摘み手 (扱えない)。
_BAKER = 3
_PICKER = 1


@pytest.fixture(scope="module")
def town() -> Any:
    return create_world_runtime(str(_SCENARIO))


def _oven_line(runtime: Any, player_id: int) -> str:
    """その人のプロンプトに出る、石窯の行。"""
    from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (  # noqa: E501,F401
        SpotGraphToolExecutor,
    )

    runtime.do_move(PlayerId(player_id), "bake_house")
    for _ in range(_TRAVEL_TICKS):
        runtime.advance_tick()
    context = runtime.build_llm_context(PlayerId(player_id))
    text = context.current_state_text
    for line in text.splitlines():
        if '"石窯"' in line:
            return line
    raise AssertionError(f"石窯の行がプロンプトに無い (player_id={player_id})")


#: 広場からかまど小屋までの道のり (シナリオ宣言と同じ)。
_TRAVEL_TICKS = 2


class TestAnObjectYouCannotUseSaysSo:
    """扱えない物体が、黙って操作を消すのではなく、扱えないと告げる。"""

    def test_the_baker_sees_the_action(self, town) -> None:
        """扱える人には、操作がそのまま出る (**正の対照**)。

        これが無いと、下の検査は「石窯に操作が 1 つも宣言されていない」でも
        緑になる。
        """
        assert "bake_bread" in _oven_line(town, _BAKER)

    def test_the_picker_is_told_who_can_use_it(self, town) -> None:
        """扱えない人には、操作の代わりに**誰なら扱えるか**が出る。

        黙って消すと、**表示が空なのに「表示から選べ」と言われる**状態になり、
        エージェントは動詞を発明する。

        文面は当初「いまのあなたに扱える操作はない」だった。実 run で摘み手が
        窯の使い方を教わる取引を受けて 10 手番待った (生業は変えられないので
        永久に焼けない) ため、**待てば変わると読める文をやめ、誰に頼めば
        よいかを言う**形にした。呼び名はシナリオが宣言したものだけを使う。
        """
        line = _oven_line(town, _PICKER)

        assert "bake_bread" not in line
        assert "焼き手だけが扱える" in line

    def test_the_note_does_not_claim_a_reason(self, town) -> None:
        """注記は engine が理由を推測しない。

        落ちた理由は職能とは限らず、世界の状態のこともある。**engine が
        推測すると別の嘘になる。**

        誰なら扱えるかを出せるのは、**シナリオが「その属性は変えられない」と
        宣言し、値の呼び名まで書いた**場合だけ。engine が属性の種類を決め打ち
        すると、種族を同じ経路に通したときに「エルフの仕事」になる。
        """
        line = _oven_line(town, _PICKER)

        assert "仕事" not in line
        assert "職能" not in line


class TestTheRefusalDoesNotReadAsANameProblem:
    """拒否の文が、2 つの誤読をどちらも塞ぐ。"""

    def test_it_says_both_that_the_name_is_absent_and_that_names_do_not_help(
        self, town,
    ) -> None:
        """「その名前は無い」と「名前を変えても通らない」を両方言う。

        **どちらか一方だけだと、別の誤読が生まれる。**

        - 名前に触れない → 「実在するが権限が無い」と読んで同じ名前で再試行
        - 名前の話で終える → 「名前を直せば通る」と読む (実 run の 5 件)
        """
        from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (  # noqa: E501
            SpotGraphToolExecutor,
        )

        message = _refusal_message(town, _PICKER)

        assert "という名前の操作はありません" in message
        assert "名前を変えても" in message


def _refusal_message(runtime: Any, player_id: int) -> str:
    """扱えない物体へ、存在しない操作名を送ったときの結果文。"""
    from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (  # noqa: E501
        SpotGraphToolExecutor,
    )
    from ai_rpg_world.application.world_graph.spot_graph_world_services import (
        SpotGraphWorldServices,
    )
    from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
        GameEndConditionEvaluator,
    )

    runtime.do_move(PlayerId(player_id), "bake_house")
    for _ in range(_TRAVEL_TICKS):
        runtime.advance_tick()
    executor = SpotGraphToolExecutor(
        spot_graph_world_services=SpotGraphWorldServices(
            interaction=runtime._interaction_service,
            exploration=runtime._exploration_service,
            world_flags=runtime._world_flag_state,
            game_end_evaluator=GameEndConditionEvaluator(),
            exploration_progress=runtime._exploration_progress,
            movement=runtime._movement_service,
        ),
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        runtime=runtime,
    )
    oven_id = runtime.id_mapper.get_int("object", "stone_oven")
    result = executor._interact(
        player_id, {"object_id": oven_id, "action_name": "examine"},
    )
    return result.message



class TestTheNoteNeverLeaksWhyItIsHidden:
    """存在層で伏せた操作については、注記そのものを出さない。"""

    def test_an_object_hidden_only_by_plane_gets_no_note(
        self, tmp_path: Path,
    ) -> None:
        """存在層だけで操作が消えた物体には、注記を出さない。

        注記を出すと**「別の存在層にだけ見える操作がある」ことを漏らす**。
        職能違いは伝えてよいが、存在層は伝えてはいけない。**同じ「操作が
        消えた」でも、理由によって見せてよいものが違う。**

        生者から見て、幽霊専用に宣言した物体を使う。宣言そのものは既存
        シナリオに無いので、この試験の中で作る。
        """
        raw: Dict[str, Any] = json.loads(_SCENARIO.read_text(encoding="utf-8"))
        board = _find_object(raw, "market_stall")
        for interaction in board["interactions"]:
            interaction["allowed_actor_planes"] = ["DEPARTED"]
        path = tmp_path / "town.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(str(path))

        text = runtime.build_llm_context(PlayerId(_PICKER)).current_state_text

        assert '"商人の屋台"' in text, "物体そのものは見えているはず"
        assert "扱える操作はない" not in text


def _find_object(raw: Dict[str, Any], object_id: str) -> Dict[str, Any]:
    for spot in raw["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            if obj["id"] == object_id:
                return obj
    raise AssertionError(f"{object_id} が見つからない")
