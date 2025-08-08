from __future__ import annotations

"""
LLM に渡されるメッセージ（system/user）を表示するデモ。
実際の LLM 呼び出しは行わず、直前の入力メッセージを標準出力に出す。
"""

import json
from typing import List, Dict

from game.core.game_context import GameContext
from game.player.player_manager import PlayerManager
from game.player.player import Player
from game.enums import Role
from game.world.spot_manager import SpotManager
from game.world.spot import Spot
from game.action.action_orchestrator import ActionOrchestrator
from game.llm.policy.llm_decision_engine import LLMDecisionEngine
from game.llm.memory import PlayerMemoryStore, ObservationMessage


def _get_messages(engine: LLMDecisionEngine, player_id: str) -> List[Dict[str, str]]:
    """公開ヘルパー経由で実際に渡される messages を取得する。"""
    return engine.get_messages_preview(player_id)


def main() -> None:
    # シンプルなワールドを構築
    player_manager = PlayerManager()
    spot_manager = SpotManager()
    ctx = GameContext.create_basic(player_manager, spot_manager)

    # スポットを作成
    spot_a = Spot("A", "街A", "にぎやかな街")
    spot_b = Spot("B", "街B", "静かな街")
    spot_manager.add_spot(spot_a)
    spot_manager.add_spot(spot_b)
    spot_manager.get_movement_graph().add_connection("A", "B", "街道")
    spot_manager.get_movement_graph().add_connection("B", "A", "街道")

    # プレイヤーを作成
    player = Player("p1", "プレイヤー1", Role.CITIZEN)
    player.set_current_spot_id("A")
    player_manager.add_player(player)

    # オーケストレータとメモリ
    orchestrator = ActionOrchestrator(ctx)
    memory = PlayerMemoryStore()
    memory.append("p1", ObservationMessage(content="Aの噴水を見た"))

    # エンジンを作成
    engine = LLMDecisionEngine(orchestrator, memory)

    # 内部メソッドを使ってメッセージを可視化
    messages = _get_messages(engine, "p1")

    print("=== SYSTEM MESSAGE ===")
    print(messages[0]["content"])  # system
    print()
    print("=== USER MESSAGE ===")
    print(messages[1]["content"])  # user（可読テキスト）


if __name__ == "__main__":
    main()


