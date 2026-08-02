"""条件ヒントが同席者行まで届き、識別子の経路には混ざらないことを保証する。

サービスがラベルを返せても、state builder → UI builder のどこかで素の名前に
戻っていれば LLM には届かない。逆に、executor の「使える操作」列挙にラベルが
混ざると、LLM が表示文字列をそのまま action_name として
渡す往復が生まれる。**両方向**を固定する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELAY_PUZZLE = _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"

_ACTOR = PlayerId(1)
_VICTIM = PlayerId(2)

_STRIKE_DOWN = {
    "action_name": "strike_down",
    "display_label": "背後から襲う",
    "preconditions": [
        {
            "condition_type": "SPOT_LIGHTING_IS",
            "required_lighting": "DARK",
            "failure_message": "明るすぎる。誰かに見られる。",
        },
        {
            "condition_type": "HAS_ITEM",
            "required_item": "knife",
            "failure_message": "素手では無理だ。",
        },
    ],
    "effects": [{
        "effect_type": "APPLY_DAMAGE",
        "target": "TARGET_PLAYER",
        "parameters": {"damage": 999},
    }],
}


@pytest.fixture()
def runtime(tmp_path: Path):
    """暗所限定・ナイフ必須の対人 action を宣言し、二人を同席させた runtime。"""
    scenario = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
    scenario["item_specs"].append({
        "id": "knife",
        "name": "ナイフ",
        "description": "よく研がれている。",
        "category": "TOOL",
    })
    scenario["player_interactions"] = [_STRIKE_DOWN]
    path = tmp_path / "relay_with_strike.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    rt = create_world_runtime(path)
    graph = rt._spot_graph_repo.find_graph()
    spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    graph.unplace_entity(EntityId.create(int(_VICTIM)))
    graph.place_entity(EntityId.create(int(_VICTIM)), spot)
    rt._spot_graph_repo.save(graph)
    return rt


class TestHintsReachTheCoLocatedPlayerRow:
    """同席者行に、条件つきの action 候補が出る。"""

    def test_row_shows_the_conditions_alongside_the_action(self, runtime) -> None:
        """相手の行末に意味・識別子・条件ヒントが一続きで並ぶ。

        ラベルは **行ごと** に持つ (snapshot 単位の 1 本のタプルではない)。
        全員に同じ一覧を出すと、使えない相手の行にも並んでしまう。
        """
        snapshot = runtime._state_builder.build_snapshot(int(_ACTOR))
        target_entry = next(
            e for e in snapshot.nearby_entities if int(e.entity_id) == int(_VICTIM)
        )

        assert (
            "背後から襲う (strike_down・暗い場所のみ・ナイフが要る・いまは薄暗い)"
            in target_entry.available_action_labels
        )

        observation = runtime.build_observation(_ACTOR)
        assert (
            "[背後から襲う (strike_down・暗い場所のみ・ナイフが要る・いまは薄暗い)]"
            in observation
        )


class TestIdentifierPathStaysBare:
    """識別子を出す経路にはヒントを混ぜない。"""

    def test_available_player_action_names_has_no_decoration(self, runtime) -> None:
        """executor が列挙する操作名は素のままである。

        ここに装飾が混ざると、LLM は装飾ごと action_name として渡し、
        「そんな操作は無い」を繰り返す。

        行為者を渡す。渡さずに全件を返していたため、クルーが操作名を
        打ち間違えると襲う手の名前が案内から漏れていた。
        """
        assert runtime.available_player_action_names(_ACTOR) == ("strike_down",)
