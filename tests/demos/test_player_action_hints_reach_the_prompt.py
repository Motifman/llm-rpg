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
        {
            "condition_type": "TARGET_PLAYER_STATE_IS",
            "required_state": {"role": "crew"},
            "failure_message": "相手の役割が条件に合わない。",
        },
    ],
    "effects": [{
        "effect_type": "APPLY_DAMAGE",
        "target": "TARGET_PLAYER",
        "parameters": {"damage": 999},
    }],
}

_STRIKE_DOWN_IN_LIGHT = {
    **_STRIKE_DOWN,
    "action_name": "strike_down_in_light",
    "display_label": "人目の前で襲う",
    "preconditions": [
        {
            "condition_type": "SPOT_LIGHTING_IS_NOT",
            "required_lighting": "DARK",
            "failure_message": "暗すぎて狙いを定められない。",
        },
        {
            "condition_type": "HAS_ITEM",
            "required_item": "knife",
            "failure_message": "素手では無理だ。",
        },
    ],
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
    scenario["players"][0].setdefault("initial_items", []).append("knife")
    scenario["player_interactions"] = [_STRIKE_DOWN, _STRIKE_DOWN_IN_LIGHT]
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

    def test_available_and_blocked_actions_are_rendered_on_separate_lines(
        self, runtime
    ) -> None:
        """成立する対人操作は行末、不成立の操作は次の「いまできない」へ分ける。

        ラベルは **行ごと** に持つ (snapshot 単位の 1 本のタプルではない)。
        全員に同じ一覧を出すと、使えない相手の行にも並んでしまう。
        """
        lines = runtime.build_observation(_ACTOR).splitlines()
        row_index = next(i for i, line in enumerate(lines) if '"リン"' in line)
        player_row = lines[row_index]
        blocked_row = lines[row_index + 1]

        assert (
            '人目の前で襲う → "strike_down_in_light"（暗い場所不可・ナイフが要る）'
            in player_row
        )
        assert "いまは" not in player_row
        assert blocked_row == (
            '      いまできない: 背後から襲う → "strike_down"'
            "（暗い場所のみ・ナイフが要る・いまは薄暗い）"
        )

    def test_target_secret_never_appears_in_either_player_action_line(
        self, runtime
    ) -> None:
        """対象の秘匿条件は候補にも阻害理由にも漏らさない。"""
        observation = runtime.build_observation(_ACTOR)

        assert "TARGET_PLAYER_STATE_IS" not in observation
        assert "相手の役割が条件に合わない" not in observation


class TestIdentifierPathStaysBare:
    """識別子を出す経路にはヒントを混ぜない。"""

    def test_available_player_action_names_has_no_decoration(self, runtime) -> None:
        """executor が列挙する操作名は素のままである。

        ここに装飾が混ざると、LLM は装飾ごと action_name として渡し、
        「そんな操作は無い」を繰り返す。

        行為者を渡す。渡さずに全件を返していたため、クルーが操作名を
        打ち間違えると襲う手の名前が案内から漏れていた。
        """
        assert runtime.available_player_action_names(_ACTOR) == (
            "strike_down",
            "strike_down_in_light",
        )
