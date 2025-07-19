from typing import Dict, List
from ..models.spot import Spot
from ..models.agent import Agent
from ..models.action import Movement, Exploration, Action, Interaction, InteractionType, ItemUsage, PostTrade, ViewTrades, AcceptTrade, CancelTrade
from ..models.interactable import Door
from ..models.item import ConsumableItem
from ..models.trade import TradeOffer
from ..systems.trading_post import TradingPost


class World:
    """
    WorldはSpotとAgentの集合体
    SpotはWorldの中の場所で、AgentはWorldの中を移動する
    WorldはAgentのSpot間の移動を管理する
    """
    def __init__(self):
        self.spots: Dict[str, Spot] = {}
        self.agents: Dict[str, Agent] = {}
        self.trading_post: TradingPost = TradingPost()  # グローバル取引所
        
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

    def get_trading_post(self) -> TradingPost:
        """取引所を取得"""
        return self.trading_post

    def execute_agent_movement(self, agent_id: str, movement: Movement):
        """
        移動行動を実行し、エージェントの現在の位置を更新
        """
        agent = self.get_agent(agent_id)
        agent.set_current_spot_id(movement.target_spot_id)
    
    def execute_agent_exploration(self, agent_id: str, exploration: Exploration):
        """
        探索行動を実行し、探索の結果をエージェントの状態に反映
        - アイテムを取得する場合はエージェントのアイテムリストに追加
        - 探索情報を取得する場合はエージェントの探索情報リストに追加
        - 経験値を取得する場合はエージェントの経験値を更新
        - お金を取得する場合はエージェントの所持金を更新
        """
        agent = self.get_agent(agent_id)
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
    
    def execute_agent_interaction(self, agent_id: str, interaction: Interaction):
        """
        相互作用行動を実行し、相互作用の結果をAgentとオブジェクトの状態に反映
        """
        agent = self.get_agent(agent_id)
        spot = self.get_spot(agent.get_current_spot_id())
        interactable = spot.get_interactable_by_id(interaction.object_id)
        
        if not interactable:
            raise ValueError(f"オブジェクト {interaction.object_id} が見つかりません")
        
        if not interactable.can_interact(agent, interaction.interaction_type):
            if interaction.required_item_id and not agent.has_item(interaction.required_item_id):
                raise ValueError(f"アイテム '{interaction.required_item_id}' が必要です")
            else:
                raise ValueError(f"この相互作用は実行できません: {interaction.description}")
        
        # オブジェクトの状態変更
        for key, value in interaction.state_changes.items():
            interactable.set_state(key, value)
        
        # 報酬の付与
        reward = interaction.reward
        for item_id in reward.items:
            if hasattr(interactable, 'items'):
                for item in interactable.items[:]:
                    if item.item_id == item_id:
                        interactable.items.remove(item)
                        agent.add_item(item)
                        break
            else:
                item = spot.get_item_by_id(item_id)
                if item:
                    spot.remove_item(item)
                    agent.add_item(item)
        
        if reward.money > 0:
            agent.add_money(reward.money)
        
        if reward.experience > 0:
            agent.add_experience_points(reward.experience)
        
        for info in reward.information:
            agent.add_discovered_info(info)
        
        # ドアのOPEN処理時の特別な処理
        if (isinstance(interactable, Door) and 
            interaction.interaction_type == InteractionType.OPEN):
            # ドアを開いた後、双方向の移動を追加
            self._add_bidirectional_door_movement(spot, interactable)
    
    def execute_agent_item_usage(self, agent_id: str, item_usage: ItemUsage):
        """
        アイテム使用行動を実行し、アイテムの効果をエージェントに適用
        """
        agent = self.get_agent(agent_id)
        
        # 使用可能性チェック
        if not item_usage.is_valid(agent):
            item_count = agent.get_item_count(item_usage.item_id)
            if item_count == 0:
                raise ValueError(f"アイテム '{item_usage.item_id}' を所持していません")
            else:
                raise ValueError(f"アイテム '{item_usage.item_id}' が不足しています（必要: {item_usage.count}個、所持: {item_count}個）")
        
        # 使用するアイテムを取得
        item = agent.get_item_by_id(item_usage.item_id)
        if not item:
            raise ValueError(f"アイテム '{item_usage.item_id}' が見つかりません")
        
        # 消費可能アイテムかチェック
        if not isinstance(item, ConsumableItem):
            raise ValueError(f"アイテム '{item_usage.item_id}' は消費できません")
        
        # アイテムを消費
        removed_count = agent.remove_item_by_id(item_usage.item_id, item_usage.count)
        if removed_count != item_usage.count:
            raise ValueError(f"アイテムの削除に失敗しました（削除予定: {item_usage.count}個、実際の削除: {removed_count}個）")
        
        # 効果を適用（使用回数分）
        for _ in range(item_usage.count):
            agent.apply_item_effect(item.effect)
    
    def execute_agent_post_trade(self, agent_id: str, post_trade: PostTrade) -> str:
        """
        取引出品行動を実行し、取引所に出品する
        
        Returns:
            取引ID
        """
        agent = self.get_agent(agent_id)
        
        # 出品可能性チェック
        if not post_trade.is_valid(agent):
            item_count = agent.get_item_count(post_trade.offered_item_id)
            if item_count == 0:
                raise ValueError(f"アイテム '{post_trade.offered_item_id}' を所持していません")
            elif item_count < post_trade.offered_item_count:
                raise ValueError(f"アイテム '{post_trade.offered_item_id}' が不足しています（必要: {post_trade.offered_item_count}個、所持: {item_count}個）")
            else:
                raise ValueError("無効な取引内容です")
        
        # TradeOfferを作成
        if post_trade.is_money_trade():
            trade_offer = TradeOffer.create_money_trade(
                seller_id=agent_id,
                offered_item_id=post_trade.offered_item_id,
                offered_item_count=post_trade.offered_item_count,
                requested_money=post_trade.requested_money,
                trade_type=post_trade.get_trade_type(),
                target_agent_id=post_trade.target_agent_id
            )
        else:
            trade_offer = TradeOffer.create_item_trade(
                seller_id=agent_id,
                offered_item_id=post_trade.offered_item_id,
                offered_item_count=post_trade.offered_item_count,
                requested_item_id=post_trade.requested_item_id,
                requested_item_count=post_trade.requested_item_count,
                trade_type=post_trade.get_trade_type(),
                target_agent_id=post_trade.target_agent_id
            )
        
        # 取引所に出品
        success = self.trading_post.post_trade(trade_offer)
        if not success:
            raise ValueError("取引の出品に失敗しました")
        
        # 出品したアイテムをエージェントから削除（エスクロー）
        removed_count = agent.remove_item_by_id(post_trade.offered_item_id, post_trade.offered_item_count)
        if removed_count != post_trade.offered_item_count:
            # 出品をキャンセルして元に戻す
            self.trading_post.cancel_trade(trade_offer.trade_id, agent_id)
            raise ValueError("アイテムの出品処理に失敗しました")
        
        return trade_offer.trade_id
    
    def execute_agent_view_trades(self, agent_id: str, view_trades: ViewTrades) -> List[TradeOffer]:
        """
        取引閲覧行動を実行し、フィルタリングされた取引一覧を返す
        """
        filters = view_trades.get_filters(agent_id)
        return self.trading_post.view_trades(filters)
    
    def execute_agent_accept_trade(self, agent_id: str, accept_trade: AcceptTrade) -> TradeOffer:
        """
        取引受託行動を実行し、取引を成立させる
        """
        agent = self.get_agent(agent_id)
        trade_id = accept_trade.get_trade_id()
        
        # 取引を取得
        trade = self.trading_post.get_trade(trade_id)
        if not trade:
            raise ValueError(f"取引 {trade_id} が見つかりません")
        
        # 受託可能性チェック
        if not trade.can_be_accepted_by(agent_id):
            if trade.seller_id == agent_id:
                raise ValueError("自分の出品は受託できません")
            else:
                raise ValueError("この取引は受託できません")
        
        # 支払い能力チェック
        if trade.is_money_trade():
            if agent.get_money() < trade.requested_money:
                raise ValueError(f"所持金が不足しています（必要: {trade.requested_money}ゴールド、所持: {agent.get_money()}ゴールド）")
        else:
            # アイテム取引の場合
            if not agent.has_item(trade.requested_item_id):
                raise ValueError(f"アイテム '{trade.requested_item_id}' を所持していません")
            
            item_count = agent.get_item_count(trade.requested_item_id)
            if item_count < trade.requested_item_count:
                raise ValueError(f"アイテム '{trade.requested_item_id}' が不足しています（必要: {trade.requested_item_count}個、所持: {item_count}個）")
        
        # 取引所で取引を成立させる
        completed_trade = self.trading_post.accept_trade(trade_id, agent_id)
        
        # 売り手と買い手を取得
        seller = self.get_agent(trade.seller_id)
        buyer = agent
        
        # アイテムと金銭の移動
        try:
            if trade.is_money_trade():
                # お金での取引
                buyer.add_money(-trade.requested_money)
                seller.add_money(trade.requested_money)
            else:
                # アイテム取引
                buyer.remove_item_by_id(trade.requested_item_id, trade.requested_item_count)
                # 売り手に要求されたアイテムを渡す
                requested_item = buyer.get_item_by_id(trade.requested_item_id)
                if requested_item:
                    for _ in range(trade.requested_item_count):
                        seller.add_item(requested_item)
            
            # 買い手に出品されたアイテムを渡す
            offered_item = seller.get_item_by_id(trade.offered_item_id)
            if offered_item:
                for _ in range(trade.offered_item_count):
                    buyer.add_item(offered_item)
            
        except Exception as e:
            # 取引に失敗した場合は取引をキャンセル状態に戻す
            raise ValueError(f"取引の処理中にエラーが発生しました: {e}")
        
        return completed_trade
    
    def execute_agent_cancel_trade(self, agent_id: str, cancel_trade: CancelTrade) -> bool:
        """
        取引キャンセル行動を実行し、出品をキャンセルする
        """
        agent = self.get_agent(agent_id)
        trade_id = cancel_trade.get_trade_id()
        
        # 取引を取得
        trade = self.trading_post.get_trade(trade_id)
        if not trade:
            raise ValueError(f"取引 {trade_id} が見つかりません")
        
        # キャンセル権限チェック
        if trade.seller_id != agent_id:
            raise ValueError("自分の出品のみキャンセルできます")
        
        # 取引所でキャンセル
        success = self.trading_post.cancel_trade(trade_id, agent_id)
        if not success:
            raise ValueError("取引のキャンセルに失敗しました")
        
        # エスクローされていたアイテムを返却
        offered_item = agent.get_item_by_id(trade.offered_item_id)
        if offered_item:
            for _ in range(trade.offered_item_count):
                agent.add_item(offered_item)
        
        return True
    
    def _add_bidirectional_door_movement(self, current_spot: Spot, door: Door):
        """ドア開放時に双方向の移動を追加"""
        # 現在のSpotから目標Spotへの移動
        forward_movement = door.creates_movement_when_opened()
        if forward_movement:
            current_spot.add_dynamic_movement(forward_movement)
        
        # 目標Spotから現在のSpotへの戻り移動
        target_spot = self.get_spot(door.target_spot_id)
        backward_movement = Movement(
            description=f"{door.name}を通って戻る",
            direction=f"{door.name}を通って戻る", 
            target_spot_id=current_spot.spot_id
        )
        target_spot.add_dynamic_movement(backward_movement)
    
    def execute_action(self, agent_id: str, action: Action):
        """
        行動を実行し、行動の結果をAgentの状態とSpotの状態に反映
        """
        if isinstance(action, Movement):
            self.execute_agent_movement(agent_id, action)
        elif isinstance(action, Exploration):
            self.execute_agent_exploration(agent_id, action)
        elif isinstance(action, Interaction):
            self.execute_agent_interaction(agent_id, action)
        elif isinstance(action, ItemUsage):
            self.execute_agent_item_usage(agent_id, action)
        elif isinstance(action, PostTrade):
            return self.execute_agent_post_trade(agent_id, action)
        elif isinstance(action, ViewTrades):
            return self.execute_agent_view_trades(agent_id, action)
        elif isinstance(action, AcceptTrade):
            return self.execute_agent_accept_trade(agent_id, action)
        elif isinstance(action, CancelTrade):
            return self.execute_agent_cancel_trade(agent_id, action)
        else:
            raise ValueError(f"不明な行動: {action}")