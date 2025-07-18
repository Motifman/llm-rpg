from typing import Dict, List
from ..models.spot import Spot
from ..models.agent import Agent
from ..models.action import Movement, Exploration, Action, Interaction


class World:
    """
    WorldはSpotとAgentの集合体
    SpotはWorldの中の場所で、AgentはWorldの中を移動する
    WorldはAgentのSpot間の移動を管理する
    """
    def __init__(self):
        self.spots: Dict[str, Spot] = {}
        self.agents: Dict[str, Agent] = {}
        
    def add_spot(self, spot: Spot):
        """スポットを追加"""
        self.spots[spot.spot_id] = spot

    def get_spot(self, spot_id: str) -> Spot:
        """スポットを取得"""
        return self.spots[spot_id]
    
    def get_all_spots(self) -> List[Spot]:
        """すべてのスポットを取得"""
        return list(self.spots.values())

    def add_agent(self, agent: Agent):
        """エージェントを追加"""
        self.agents[agent.agent_id] = agent

    def get_agent(self, agent_id: str) -> Agent:
        """エージェントを取得"""
        return self.agents[agent_id]

    def get_all_agents(self) -> List[Agent]:
        """すべてのエージェントを取得"""
        return list(self.agents.values())

    def execute_agent_movement(self, agent: Agent, movement: Movement):
        """
        移動行動を実行し、エージェントの現在の位置を更新
        """
        agent.set_current_spot_id(movement.target_spot_id)
    
    def execute_agent_exploration(self, agent: Agent, exploration: Exploration):
        """
        探索行動を実行し、探索の結果をエージェントの状態に反映
        - アイテムを取得する場合はエージェントのアイテムリストに追加
        - 探索情報を取得する場合はエージェントの探索情報リストに追加
        - 経験値を取得する場合はエージェントの経験値を更新
        - お金を取得する場合はエージェントの所持金を更新
        """
        if exploration.item_id:
            spot = self.get_spot(agent.get_current_spot_id())
            item = spot.get_item_by_id(exploration.item_id)
            if item:
                spot.remove_item(item)
                agent.add_item(item)
        if exploration.discovered_info:
            agent.add_discovered_info(exploration.discovered_info)
        if exploration.experience_points:
            agent.add_experience_points(exploration.experience_points)
        if exploration.money:
            agent.add_money(exploration.money)
    
    def execute_agent_interaction(self, agent: Agent, interaction: Interaction):
        """
        相互作用行動を実行し、相互作用の結果をAgentとオブジェクトの状態に反映
        """
        spot = self.get_spot(agent.get_current_spot_id())
        interactable = spot.get_interactable_by_id(interaction.object_id)
        
        if not interactable:
            raise ValueError(f"オブジェクト {interaction.object_id} が見つかりません")
        
        # 相互作用の実行可否をチェック
        if not interactable.can_interact(agent, interaction.interaction_type):
            # 必要アイテムがない場合のメッセージ
            if interaction.required_item_id and not agent.has_item(interaction.required_item_id):
                raise ValueError(f"アイテム '{interaction.required_item_id}' が必要です")
            else:
                raise ValueError(f"この相互作用は実行できません: {interaction.description}")
        
        # 報酬の付与
        reward = interaction.reward
        
        # アイテム報酬
        for item_id in reward.items:
            # InteractableObjectからアイテムを取得
            if hasattr(interactable, 'items'):
                for item in interactable.items[:]:  # リストのコピーでイテレート
                    if item.item_id == item_id:
                        interactable.items.remove(item)
                        agent.add_item(item)
                        break
            else:
                # Spotからアイテムを取得（代替）
                item = spot.get_item_by_id(item_id)
                if item:
                    spot.remove_item(item)
                    agent.add_item(item)
        
        # お金報酬
        if reward.money > 0:
            agent.add_money(reward.money)
        
        # 経験値報酬
        if reward.experience > 0:
            agent.add_experience_points(reward.experience)
        
        # 情報報酬
        for info in reward.information:
            agent.add_discovered_info(info)
        
        # オブジェクトの状態変更
        for key, value in interaction.state_changes.items():
            interactable.set_state(key, value)
    
    def execute_action(self, agent_id: str, action: Action):
        """
        行動を実行し、行動の結果をAgentの状態とSpotの状態に反映
        """
        agent = self.get_agent(agent_id)
        if isinstance(action, Movement):
            self.execute_agent_movement(agent, action)
        elif isinstance(action, Exploration):
            self.execute_agent_exploration(agent, action)
        elif isinstance(action, Interaction):
            self.execute_agent_interaction(agent, action)
        else:
            raise ValueError(f"不明な行動: {action}")