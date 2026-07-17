"""interact ツールの自由入力 ``parameters`` 配線切れ (PR-I) の回帰テスト。

背景 (#717 の E2E 作成中に発覚):
LLM ツール実行経路 ``SpotGraphToolExecutor._interact`` → ``WorldRuntime.do_interact``
→ ``SpotInteractionApplicationService.execute_interaction`` の統合リファクタ
(commit a824b510 前後) で、interact ツールの自由入力 ``parameters``
(パズルの暗証番号や看板の本文用) が ``_interact`` で一度も取り出されず
``do_interact`` に渡っていなかった。``execute_interaction`` 自体は
``interaction_parameters`` の受け口を持ち domain まで正しく転送するので、
application 層のテスト (test_sign_object_app_integration.py) は green の
ままバグが隠れていた。

本テストは ``SpotGraphToolExecutor`` (ツール実行層) → ``WorldRuntime.do_interact``
→ domain effect (WRITE_PLAYER_TEXT) までを実際に貫通させ、``parameters`` が
最後まで届くことを保証する。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_INTERACT
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario

NOTICE_BOARD_OBJECT_ID = "notice_board"
CODE_LOCK_OBJECT_ID = "code_lock"


def _scenario_with_sign_and_code_lock() -> dict:
    """看板 (text) とパズル入力 (code) の 2 種の自由入力 object を持つシナリオ。"""
    scenario = copy.deepcopy(_minimal_scenario())
    objects = scenario["spots"][0]["interior"]["objects"]
    objects.append(
        {
            "id": NOTICE_BOARD_OBJECT_ID,
            "name": "掲示板",
            "description": "誰かが書き込めそうな掲示板。",
            "object_type": "SIGN",
            "state": {},
            "interactions": [
                {
                    "action_name": "write",
                    "display_label": "書き込む",
                    "preconditions": [],
                    "effects": [
                        {"effect_type": "WRITE_PLAYER_TEXT", "parameters": {}},
                    ],
                },
            ],
        }
    )
    # パズル入力: text_param_key を "code" にすることで、看板と同じ
    # WRITE_PLAYER_TEXT 経路をパズルの暗証番号入力用に再利用する
    # (実装コメント「パズル用に既存の経路をそのまま使う」に対応する構成)。
    objects.append(
        {
            "id": CODE_LOCK_OBJECT_ID,
            "name": "暗証番号パネル",
            "description": "暗証番号を入力できそうなパネル。",
            "object_type": "SIGN",
            "state": {},
            "interactions": [
                {
                    "action_name": "input_code",
                    "display_label": "入力する",
                    "preconditions": [],
                    "effects": [
                        {
                            "effect_type": "WRITE_PLAYER_TEXT",
                            "parameters": {"text_param_key": "code"},
                        },
                    ],
                },
            ],
        }
    )
    return scenario


@pytest.fixture()
def scenario_path(tmp_path: Path) -> Path:
    path = tmp_path / "interact_parameters_wiring_scenario.json"
    path.write_text(
        json.dumps(_scenario_with_sign_and_code_lock(), ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _build_executor(runtime: Any) -> SpotGraphToolExecutor:
    """SpotGraphToolExecutor を実 WorldRuntime に紐づけて構築する。

    ``_interact`` は ``self._runtime.do_interact`` を呼ぶ薄い wrapper なので、
    movement 以外の SpotGraphWorldServices 依存は不要 (実 runtime だけ渡す)。
    """
    from unittest.mock import MagicMock

    services = SpotGraphWorldServices(
        interaction=MagicMock(),
        exploration=MagicMock(),
        world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
        game_end_evaluator=MagicMock(),
        exploration_progress=MagicMock(),
        movement=MagicMock(),
        simulation=None,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        runtime=runtime,
    )


def _object_state(runtime: Any, object_str_id: str) -> dict:
    obj_int = runtime.id_mapper.get_int("object", object_str_id)
    from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

    graph = runtime._spot_graph_repo.find_graph()
    spot_id = graph.get_entity_spot(EntityId.create(1))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    return dict(interior.get_object(SpotObjectId.create(obj_int)).state)


class TestInteractParametersReachSignEffectThroughToolExecutor:
    """看板 (WRITE_PLAYER_TEXT) への貫通: ツール実行層 → do_interact → 効果適用。"""

    def test_parameters_のtextが看板のstateまで届く(self, scenario_path: Path) -> None:
        runtime = create_world_runtime(scenario_path)
        executor = _build_executor(runtime)
        object_id = runtime.id_mapper.get_int("object", NOTICE_BOARD_OBJECT_ID)

        result = executor._interact(
            player_id=1,
            args={
                "object_id": object_id,
                "action_name": "write",
                "parameters": {"text": "水場はここから北"},
                "inner_thought": "書いておこう",
            },
        )

        assert result.success is True
        state = _object_state(runtime, NOTICE_BOARD_OBJECT_ID)
        assert state["sign_text"] == "水場はここから北"
        # 書き手名も一緒に残る (= execute_interaction まで正しく到達した証拠)
        assert state["sign_author_name"]

    def test_パズル用codeパラメータも同じ経路でstateまで届く(
        self, scenario_path: Path
    ) -> None:
        """暗証番号パネル (text_param_key=code) でも parameters が届く。

        パズル入力は key が "text" 以外 (ここでは "code") になる点が既存の
        看板テスト (test_sign_object_app_integration.py) との違い。
        """
        runtime = create_world_runtime(scenario_path)
        executor = _build_executor(runtime)
        object_id = runtime.id_mapper.get_int("object", CODE_LOCK_OBJECT_ID)

        result = executor._interact(
            player_id=1,
            args={
                "object_id": object_id,
                "action_name": "input_code",
                "parameters": {"code": "1234"},
                "inner_thought": "入力してみる",
            },
        )

        assert result.success is True
        state = _object_state(runtime, CODE_LOCK_OBJECT_ID)
        assert state["sign_text"] == "1234"

    def test_parameters未指定でも従来どおり動く(self, scenario_path: Path) -> None:
        """parameters を渡さない既存呼び出しは後方互換で動き続ける。

        WRITE_PLAYER_TEXT は text が無いと「何を書くか指定してください」の
        案内メッセージを返す仕様 (effect_service 側の既存挙動)。ここでは
        例外を投げず success=True のまま案内が返ることを確認する。
        """
        runtime = create_world_runtime(scenario_path)
        executor = _build_executor(runtime)
        object_id = runtime.id_mapper.get_int("object", NOTICE_BOARD_OBJECT_ID)

        result = executor._interact(
            player_id=1,
            args={
                "object_id": object_id,
                "action_name": "write",
                "inner_thought": "何もパラメータを渡さない",
            },
        )

        assert result.success is True
        assert "text" in result.message
        state = _object_state(runtime, NOTICE_BOARD_OBJECT_ID)
        assert "sign_text" not in state

    def test_parameters_が不正型なら例外にならずNoneとして扱われる(
        self, scenario_path: Path
    ) -> None:
        """dict でない parameters (例: 文字列) は落とさず None 扱いにする。"""
        runtime = create_world_runtime(scenario_path)
        executor = _build_executor(runtime)
        object_id = runtime.id_mapper.get_int("object", NOTICE_BOARD_OBJECT_ID)

        result = executor._interact(
            player_id=1,
            args={
                "object_id": object_id,
                "action_name": "write",
                "parameters": "not-a-dict",
                "inner_thought": "型がおかしいパラメータ",
            },
        )

        assert result.success is True
        state = _object_state(runtime, NOTICE_BOARD_OBJECT_ID)
        assert "sign_text" not in state
