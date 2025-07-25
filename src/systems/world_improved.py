from typing import Dict, List, Optional, Any
from ..models.spot import Spot
from ..models.agent import Agent
from ..models.movement_graph import MovementGraph
from ..models.movement_validator import MovementValidator
from ..models.movement_cache import MovementCache
from ..models.spot_action import ActionResult
from ..systems.trading_post import TradingPost
from ..systems.battle import BattleManager
from ..systems.quest_system import QuestSystem


class ImprovedWorld:
    """改善されたWorldクラス"""
    
    def __init__(self):
        # 基本システム
        self.spots: Dict[str, Spot] = {}
        self.agents: Dict[str, Agent] = {}
        self.trading_post: TradingPost = TradingPost()
        self.battle_manager: BattleManager = BattleManager()
        self.quest_system: QuestSystem = QuestSystem()
        
        # 改善された移動システム
        self.movement_graph: MovementGraph = MovementGraph()
        self.movement_cache: MovementCache = MovementCache(self.movement_graph)
        self.movement_validator: MovementValidator = MovementValidator(self.movement_graph)
        
        # 統計情報
        self.movement_stats: Dict[str, any] = {}
    
    def add_spot(self, spot: Spot):
        """Spotを追加"""
        self.spots[spot.spot_id] = spot
        self.movement_graph.add_spot(spot)
        
        # 統計情報を更新
        self._update_movement_stats()
    
    def add_connection(self, from_spot_id: str, to_spot_id: str, 
                      direction: str, description: str, 
                      is_bidirectional: bool = True, 
                      conditions: Dict[str, any] = None,
                      is_dynamic: bool = False) -> bool:
        """移動接続を追加（基本的なバリデーション付き）"""
        
        # 基本的な存在チェックのみ実行
        if from_spot_id not in self.spots:
            print(f"移動接続の追加に失敗: Spot {from_spot_id} が存在しません")
            return False
        
        if to_spot_id not in self.spots:
            print(f"移動接続の追加に失敗: Spot {to_spot_id} が存在しません")
            return False
        
        # 接続を追加
        success = self.movement_cache.add_connection(
            from_spot_id, to_spot_id, direction, description,
            is_bidirectional, conditions, is_dynamic
        )
        
        if success:
            self._update_movement_stats()
            print(f"✅ 接続を追加しました: {from_spot_id} --{direction}--> {to_spot_id}")
        else:
            print(f"❌ 接続の追加に失敗しました: {from_spot_id} --{direction}--> {to_spot_id}")
        
        return success
    
    def remove_connection(self, from_spot_id: str, to_spot_id: str, direction: str):
        """移動接続を削除"""
        self.movement_cache.remove_connection(from_spot_id, to_spot_id, direction)
        self._update_movement_stats()
    
    def get_available_actions_for_agent(self, agent_id: str) -> Dict[str, Any]:
        """エージェントが実行可能な行動を取得（キャッシュ使用）"""
        agent = self.get_agent(agent_id)
        spot = self.get_spot(agent.get_current_spot_id())
        
        # キャッシュを使用して移動可能先を取得
        movements = self.movement_cache.get_available_movements(spot.spot_id, agent)
        
        # SpotActionを取得
        spot_actions = spot.get_available_spot_actions(agent, self)
        
        return {
            "agent_id": agent_id,
            "current_spot": {
                "spot_id": spot.spot_id,
                "name": spot.name,
                "description": spot.description
            },
            "available_movements": movements,
            "available_spot_actions": spot_actions,
            "total_actions": len(movements) + len(spot_actions)
        }
    
    def execute_spot_action(self, agent_id: str, action_id: str) -> ActionResult:
        """SpotActionを実行"""
        agent = self.get_agent(agent_id)
        spot = self.get_spot(agent.get_current_spot_id())
        
        # 移動行動の場合
        if action_id.startswith("movement_"):
            return self._execute_movement_action(agent, spot, action_id)
        
        # その他のSpotAction
        result = spot.execute_spot_action(action_id, agent, self)
        
        # 移動後の攻撃的モンスターとの遭遇チェック
        if result.success and action_id.startswith("movement_"):
            self.check_aggressive_monster_encounters(agent_id)
        
        return result
    
    def _execute_movement_action(self, agent, spot, action_id: str) -> ActionResult:
        """移動行動を実行"""
        direction = action_id.replace("movement_", "")
        
        # 移動可能先から該当する移動を検索
        movements = self.movement_cache.get_available_movements(spot.spot_id, agent)
        target_movement = None
        
        for movement in movements:
            if movement.direction == direction:
                target_movement = movement
                break
        
        if not target_movement:
            return ActionResult(
                success=False,
                message=f"移動行動 {direction} が見つかりません",
                warnings=[],
                state_changes={}
            )
        
        # 移動の妥当性を検証（接続が存在する場合のみ）
        is_valid, errors = self.movement_validator.validate_movement(
            spot.spot_id, target_movement.target_spot_id, direction, agent
        )
        
        if not is_valid:
            return ActionResult(
                success=False,
                message=f"移動に失敗しました: {'; '.join(errors)}",
                warnings=[],
                state_changes={}
            )
        
        # 移動実行
        old_spot_id = agent.get_current_spot_id()
        agent.set_current_spot_id(target_movement.target_spot_id)
        
        return ActionResult(
            success=True,
            message=f"{spot.name}から{target_movement.description}に移動しました",
            warnings=[],
            state_changes={
                "agent_location": {
                    "old_spot_id": old_spot_id,
                    "new_spot_id": target_movement.target_spot_id
                }
            }
        )
    
    def validate_world(self) -> List[str]:
        """ワールド全体の妥当性を検証"""
        errors = []
        
        # 移動グラフの検証
        graph_errors = self.movement_validator.validate_graph()
        errors.extend(graph_errors)
        
        # 孤立したSpotのチェック
        for spot_id in self.spots:
            has_outgoing = self.movement_cache.get_connected_spots(spot_id)
            has_incoming = self.movement_cache.get_reverse_connections(spot_id)
            if not has_outgoing and not has_incoming:
                errors.append(f"Spot {spot_id} は孤立しています")
        
        # エージェントの位置の妥当性チェック
        for agent_id, agent in self.agents.items():
            current_spot_id = agent.get_current_spot_id()
            if current_spot_id not in self.spots:
                errors.append(f"エージェント {agent_id} の位置 {current_spot_id} が無効です")
        
        return errors
    
    def get_shortest_path(self, from_spot_id: str, to_spot_id: str) -> Optional[List[str]]:
        """最短経路を取得"""
        return self.movement_graph.get_shortest_path(from_spot_id, to_spot_id)
    
    def get_alternative_routes(self, from_spot_id: str, to_spot_id: str, 
                             max_routes: int = 3) -> List[List[str]]:
        """代替経路を取得"""
        return self.movement_validator.get_alternative_routes(from_spot_id, to_spot_id, max_routes)
    
    def get_movement_statistics(self) -> Dict[str, any]:
        """移動統計情報を取得"""
        return self.movement_cache.get_movement_statistics()
    
    def _update_movement_stats(self):
        """移動統計情報を更新"""
        self.movement_stats = self.movement_cache.get_movement_statistics()
    
    # === 既存メソッドの互換性維持 ===
    
    def get_spot(self, spot_id: str) -> Optional[Spot]:
        """Spotを取得"""
        return self.spots.get(spot_id)
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Agentを取得"""
        return self.agents.get(agent_id)
    
    def add_agent(self, agent: Agent):
        """Agentを追加"""
        self.agents[agent.agent_id] = agent
    
    def check_aggressive_monster_encounters(self, agent_id: str):
        """攻撃的モンスターとの遭遇チェック"""
        agent = self.get_agent(agent_id)
        if not agent:
            return
        
        current_spot = self.get_spot(agent.get_current_spot_id())
        if not current_spot:
            return
        
        aggressive_monsters = current_spot.get_aggressive_monsters()
        if aggressive_monsters:
            # 戦闘システムとの連携
            print(f"攻撃的モンスターと遭遇: {[m.name for m in aggressive_monsters]}")
    
    def get_world_info(self) -> Dict[str, any]:
        """ワールド情報を取得"""
        return {
            "total_spots": len(self.spots),
            "total_agents": len(self.agents),
            "movement_statistics": self.get_movement_statistics(),
            "validation_errors": self.validate_world()
        } 