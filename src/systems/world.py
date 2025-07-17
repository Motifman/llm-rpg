from typing import Dict, List
from ..models.spot import Spot
from ..models.agent import Agent


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

    def execute_agent_movement(self, agent_id: str, action: str) -> bool:
        """
        エージェントの現在の位置を指定されたアクションで移動
        移動の成否を返す
        """
        agent = self.get_agent(agent_id)
        current_spot_id = agent.get_current_spot_id()
        current_spot = self.get_spot(current_spot_id)
        
        # 階層的移動システムを使用
        available_movements = current_spot.get_available_movements()
        if action not in available_movements:
            return False
        
        new_spot_id = available_movements[action]
        agent.set_current_spot_id(new_spot_id)
        return True