from typing import Dict, List, Optional, Any
from ..models.spot import Spot
from ..models.agent import Agent
from ..models.action import Movement, Exploration, Action, Interaction, InteractionType, ItemUsage, PostTrade, ViewTrades, AcceptTrade, CancelTrade, Conversation, AttackMonster, DefendBattle, EscapeBattle, StartBattle, JoinBattle, CraftItem, EnhanceItem, LearnRecipe, SetupShop, ProvideService, PriceNegotiation, GatherResource, ProcessMaterial, ManageFarm, AdvancedCombat, ViewAvailableQuests, AcceptQuest, CancelQuest, ViewQuestProgress, SubmitQuest, RegisterToGuild, PostQuestToGuild, WriteDiary, ReadDiary, Sleep, GrantHomePermission, StoreItem, RetrieveItem, SellItem, BuyItem, SetItemPrice, ManageInventory, ProvideLodging, ProvideDance, ProvidePrayer
from ..models.interactable import Door
from ..models.item import ConsumableItem
from ..models.trade import TradeOffer
from ..models.monster import Monster, MonsterType
from ..models.job import JobAgent, CraftsmanAgent, MerchantAgent, AdventurerAgent, ProducerAgent, ServiceProviderAgent, TraderAgent
from ..models.quest import Quest, QuestType, QuestDifficulty
from ..models.home import Home, HomePermission
from ..models.home_interactables import Bed, Desk
from ..systems.trading_post import TradingPost
from ..systems.message import LocationChatMessage
from ..systems.battle import BattleManager, Battle, BattleResult
from ..systems.quest_system import QuestSystem


class World:
    """
    WorldはSpotとAgentの集合体
    SpotはWorldの中の場所で、AgentはWorldの中を移動する
    WorldはAgentのSpot間の移動を管理する
    """
    def __init__(self):
        self.spots: Dict[str, Spot] = {}
        self.agents: Dict[str, Agent] = {}
        self.trading_post: TradingPost = TradingPost()
        self.battle_manager: BattleManager = BattleManager()
        self.monsters: Dict[str, Monster] = {}  # グローバルモンスター管理
        self.quest_system: QuestSystem = QuestSystem()  # クエストシステム
        
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

    def add_monster(self, monster: Monster, spot_id: str):
        """モンスターを追加"""
        self.monsters[monster.monster_id] = monster
        spot = self.get_spot(spot_id)
        spot.add_monster(monster)

    def get_monster(self, monster_id: str) -> Monster:
        """モンスターを取得"""
        return self.monsters[monster_id]

    def get_all_monsters(self) -> List[Monster]:
        """すべてのモンスターを取得"""
        return list(self.monsters.values())

    def get_battle_manager(self) -> BattleManager:
        """バトルマネージャーを取得"""
        return self.battle_manager

    def get_quest_system(self) -> QuestSystem:
        """クエストシステムを取得"""
        return self.quest_system

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
        - 隠れているモンスターを発見する場合がある
        """
        agent = self.get_agent(agent_id)
        spot = self.get_spot(agent.get_current_spot_id())
        
        # 既存の探索機能
        if exploration.item_id:
            item = spot.get_item_by_id(exploration.item_id)
            if item:
                spot.remove_item(item)
                agent.add_item(item)
                # アイテム取得時のクエスト進捗更新
                self._update_quest_progress_on_item_get(agent_id, exploration.item_id)
        if exploration.discovered_info:
            agent.add_discovered_info(exploration.discovered_info)
        if exploration.experience_points:
            agent.add_experience_points(exploration.experience_points)
        if exploration.money:
            agent.add_money(exploration.money)
        
        # 場所訪問時のクエスト進捗更新
        self._update_quest_progress_on_location_visit(agent_id, agent.get_current_spot_id())
        
        # モンスター発見機能
        self._check_for_hidden_monsters(agent, spot)
    
    def _check_for_hidden_monsters(self, agent: Agent, spot: Spot):
        """探索時に隠れているモンスターを発見する可能性をチェック"""
        import random
        
        # 隠れているモンスターがいる場合
        if spot.hidden_monsters:
            # 30%の確率でモンスターを発見
            if random.random() < 0.3:
                # ランダムに隠れているモンスターを1体発見
                hidden_monster_ids = list(spot.hidden_monsters.keys())
                discovered_monster_id = random.choice(hidden_monster_ids)
                
                # モンスターを発見状態にする
                spot.reveal_hidden_monster(discovered_monster_id)
                monster = spot.get_monster_by_id(discovered_monster_id)
                
                # エージェントに発見情報を追加
                discovery_info = f"探索中に {monster.name} を発見した！"
                agent.add_discovered_info(discovery_info)
    
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
    
    def get_agents_in_spot(self, spot_id: str) -> List[Agent]:
        """指定されたスポットにいるエージェントのリストを取得"""
        agents_in_spot = []
        for agent in self.agents.values():
            if agent.get_current_spot_id() == spot_id:
                agents_in_spot.append(agent)
        return agents_in_spot
    
    def execute_agent_conversation(self, agent_id: str, conversation: Conversation):
        """
        会話行動を実行し、同じスポットにいるエージェントにメッセージを配信
        """
        sender = self.get_agent(agent_id)
        current_spot_id = sender.get_current_spot_id()

        message = LocationChatMessage(
            sender_id=agent_id,
            spot_id=current_spot_id,
            content=conversation.get_content(),
            target_agent_id=conversation.get_target_agent_id()
        )

        agents_in_spot = self.get_agents_in_spot(current_spot_id)

        for agent in agents_in_spot:
            if agent.agent_id == agent_id:
                continue
            if message.is_targeted() and agent.agent_id != message.get_target_agent_id():
                continue
            agent.receive_message(message)
        
        sender.conversation_history.append(message)
        
        return message
    
    # === バトルシステム関連 ===
    
    def execute_agent_start_battle(self, agent_id: str, start_battle: StartBattle) -> str:
        """戦闘開始行動を実行"""
        agent = self.get_agent(agent_id)
        spot = self.get_spot(agent.get_current_spot_id())
        monster = spot.get_monster_by_id(start_battle.get_monster_id())
        
        if not monster:
            raise ValueError(f"モンスター {start_battle.get_monster_id()} が見つかりません")
        
        if not monster.is_alive:
            raise ValueError(f"{monster.name} は既に倒されています")
        
        # 戦闘を開始
        battle_id = self.battle_manager.start_battle(spot.spot_id, monster, agent)
        
        # 同じスポットの他のエージェントに戦闘開始を通知
        agents_in_spot = self.get_agents_in_spot(spot.spot_id)
        for other_agent in agents_in_spot:
            if other_agent.agent_id != agent_id:
                notification = f"{agent.name} が {monster.name} との戦闘を開始しました！参加するには戦闘参加行動を選択してください。"
                other_agent.add_discovered_info(notification)
        
        return battle_id
    
    def execute_agent_join_battle(self, agent_id: str, join_battle: JoinBattle):
        """戦闘参加行動を実行"""
        agent = self.get_agent(agent_id)
        battle = self.battle_manager.get_battle(join_battle.get_battle_id())
        
        if not battle:
            raise ValueError(f"戦闘 {join_battle.get_battle_id()} が見つかりません")
        
        if battle.spot_id != agent.get_current_spot_id():
            raise ValueError("同じスポットにいないため戦闘に参加できません")
        
        # 戦闘に参加
        battle.add_participant(agent)
    
    def execute_agent_battle_action(self, agent_id: str, action) -> str:
        """戦闘中の行動を実行"""
        agent = self.get_agent(agent_id)
        current_spot_id = agent.get_current_spot_id()
        
        # 現在のスポットで進行中の戦闘を取得
        battle = self.battle_manager.get_battle_by_spot(current_spot_id)
        if not battle:
            raise ValueError("現在戦闘中ではありません")
        
        if agent_id not in battle.participants:
            raise ValueError("この戦闘に参加していません")
        
        # 戦闘行動を実行
        turn_action = battle.execute_agent_action(agent_id, action)
        
        # ターンを進める
        battle.advance_turn()
        
        # モンスターのターンの場合は自動実行
        if battle.is_monster_turn() and not battle.is_battle_finished():
            monster_action = battle.execute_monster_turn()
            battle.advance_turn()
        
        # 戦闘が終了した場合の処理
        if battle.is_battle_finished():
            result = self.battle_manager.finish_battle(battle.battle_id)
            self._handle_battle_result(result)
            return f"戦闘終了: {result.victory}"
        
        return f"戦闘継続中: {turn_action.message}"
    
    def _handle_battle_result(self, result: BattleResult):
        """戦闘結果の処理"""
        if result.victory and result.defeated_monster:
            # 勝利時の報酬配布
            for participant_id in result.participants:
                agent = self.get_agent(participant_id)
                
                # 報酬を配布
                if result.rewards:
                    for item in result.rewards.items:
                        agent.add_item(item)
                    
                    if result.rewards.money > 0:
                        agent.add_money(result.rewards.money)
                    
                    if result.rewards.experience > 0:
                        agent.add_experience_points(result.rewards.experience)
                    
                    for info in result.rewards.information:
                        agent.add_discovered_info(info)
                
                # 勝利情報を追加
                victory_info = f"{result.defeated_monster.name} を倒した！"
                agent.add_discovered_info(victory_info)
                
                # クエスト進捗更新
                self._update_quest_progress_on_monster_kill(participant_id, result.defeated_monster.monster_id)
            
            # モンスターをスポットから削除
            for spot in self.spots.values():
                if result.defeated_monster.monster_id in spot.monsters:
                    spot.remove_monster(result.defeated_monster.monster_id)
                    break
            
            # グローバルモンスターリストからも削除
            if result.defeated_monster.monster_id in self.monsters:
                del self.monsters[result.defeated_monster.monster_id]
    
    def check_aggressive_monster_encounters(self, agent_id: str):
        """エージェントの移動時に攻撃的なモンスターとの強制戦闘をチェック"""
        agent = self.get_agent(agent_id)
        spot = self.get_spot(agent.get_current_spot_id())
        
        # 攻撃的なモンスターがいる場合は強制戦闘
        aggressive_monsters = spot.get_aggressive_monsters()
        if aggressive_monsters:
            # 最初の攻撃的なモンスターと戦闘開始
            monster = aggressive_monsters[0]
            battle_id = self.battle_manager.start_battle(spot.spot_id, monster, agent)
            
            # エージェントに強制戦闘の情報を追加
            force_battle_info = f"{monster.name} が襲いかかってきた！強制的に戦闘が開始されました。"
            agent.add_discovered_info(force_battle_info)
            
            # 戦闘の最初のターンを処理（モンスターが先制の場合）
            battle = self.battle_manager.get_battle(battle_id)
            if battle and battle.is_monster_turn():
                monster_action = battle.execute_monster_turn()
                battle.advance_turn()
            
            return battle_id
        
        return None
    
    def execute_action(self, agent_id: str, action: Action):
        """
        行動を実行し、行動の結果をAgentの状態とSpotの状態に反映
        """
        if isinstance(action, Movement):
            self.execute_agent_movement(agent_id, action)
            # 移動後に攻撃的なモンスターとの強制戦闘をチェック
            self.check_aggressive_monster_encounters(agent_id)
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
        elif isinstance(action, Conversation):
            return self.execute_agent_conversation(agent_id, action)
        elif isinstance(action, StartBattle):
            return self.execute_agent_start_battle(agent_id, action)
        elif isinstance(action, JoinBattle):
            self.execute_agent_join_battle(agent_id, action)
        elif isinstance(action, (AttackMonster, DefendBattle, EscapeBattle)):
            return self.execute_agent_battle_action(agent_id, action)
        # 職業システム関連の行動
        elif isinstance(action, CraftItem):
            return self.execute_agent_craft_item(agent_id, action)
        elif isinstance(action, EnhanceItem):
            return self.execute_agent_enhance_item(agent_id, action)
        elif isinstance(action, LearnRecipe):
            return self.execute_agent_learn_recipe(agent_id, action)
        elif isinstance(action, SetupShop):
            return self.execute_agent_setup_shop(agent_id, action)
        elif isinstance(action, ProvideService):
            return self.execute_agent_provide_service(agent_id, action)
        elif isinstance(action, PriceNegotiation):
            return self.execute_agent_price_negotiation(agent_id, action)
        # 新しい商人システム関連の行動
        elif isinstance(action, SellItem):
            return self.execute_agent_sell_item(agent_id, action)
        elif isinstance(action, BuyItem):
            return self.execute_agent_buy_item(agent_id, action)
        elif isinstance(action, SetItemPrice):
            return self.execute_agent_set_item_price(agent_id, action)
        elif isinstance(action, ManageInventory):
            return self.execute_agent_manage_inventory(agent_id, action)
        elif isinstance(action, ProvideLodging):
            return self.execute_agent_provide_lodging(agent_id, action)
        elif isinstance(action, ProvideDance):
            return self.execute_agent_provide_dance(agent_id, action)
        elif isinstance(action, ProvidePrayer):
            return self.execute_agent_provide_prayer(agent_id, action)
        elif isinstance(action, GatherResource):
            return self.execute_agent_gather_resource(agent_id, action)
        elif isinstance(action, ProcessMaterial):
            return self.execute_agent_process_material(agent_id, action)
        elif isinstance(action, ManageFarm):
            return self.execute_agent_manage_farm(agent_id, action)
        elif isinstance(action, AdvancedCombat):
            return self.execute_agent_advanced_combat(agent_id, action)
        # クエストシステム関連の行動
        elif isinstance(action, ViewAvailableQuests):
            return self.execute_agent_view_available_quests(agent_id, action)
        elif isinstance(action, AcceptQuest):
            return self.execute_agent_accept_quest(agent_id, action)
        elif isinstance(action, CancelQuest):
            return self.execute_agent_cancel_quest(agent_id, action)
        elif isinstance(action, ViewQuestProgress):
            return self.execute_agent_view_quest_progress(agent_id, action)
        elif isinstance(action, SubmitQuest):
            return self.execute_agent_submit_quest(agent_id, action)
        elif isinstance(action, RegisterToGuild):
            return self.execute_agent_register_to_guild(agent_id, action)
        elif isinstance(action, PostQuestToGuild):
            return self.execute_agent_post_quest_to_guild(agent_id, action)
        # 家システム関連の行動
        elif isinstance(action, WriteDiary):
            return self.execute_agent_write_diary(agent_id, action)
        elif isinstance(action, ReadDiary):
            return self.execute_agent_read_diary(agent_id, action)
        elif isinstance(action, Sleep):
            return self.execute_agent_sleep(agent_id, action)
        elif isinstance(action, GrantHomePermission):
            return self.execute_agent_grant_home_permission(agent_id, action)
        elif isinstance(action, StoreItem):
            return self.execute_agent_store_item(agent_id, action)
        elif isinstance(action, RetrieveItem):
            return self.execute_agent_retrieve_item(agent_id, action)
        else:
            raise ValueError(f"不明な行動: {action}")
    
    # === 職業システム関連の行動実行メソッド ===
    
    def execute_agent_craft_item(self, agent_id: str, craft_action: CraftItem) -> Dict:
        """アイテム合成行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, CraftsmanAgent):
            raise ValueError(f"エージェント {agent_id} は職人ではありません")
        
        if not craft_action.is_valid(agent):
            raise ValueError("合成条件を満たしていません")
        
        recipe = agent.get_recipe_by_id(craft_action.recipe_id)
        if not recipe:
            raise ValueError(f"レシピ {craft_action.recipe_id} が見つかりません")
        
        return agent.craft_item(recipe, craft_action.quantity)
    
    def execute_agent_enhance_item(self, agent_id: str, enhance_action: EnhanceItem) -> Dict:
        """アイテム強化行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, CraftsmanAgent):
            raise ValueError(f"エージェント {agent_id} は職人ではありません")
        
        if not enhance_action.is_valid(agent):
            raise ValueError("強化条件を満たしていません")
        
        return agent.enhance_item(enhance_action.item_id, enhance_action.enhancement_materials)
    
    def execute_agent_learn_recipe(self, agent_id: str, learn_action: LearnRecipe) -> Dict:
        """レシピ習得行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, JobAgent):
            raise ValueError(f"エージェント {agent_id} は職業エージェントではありません")
        
        if not learn_action.is_valid(agent):
            raise ValueError("レシピ習得条件を満たしていません")
        
        # TODO: レシピデータベースから取得する実装が必要
        # 現在は簡易実装
        result = {
            "success": False,
            "recipe_learned": None,
            "materials_consumed": {},
            "messages": []
        }
        
        # 材料消費
        for material_id, count in learn_action.required_materials.items():
            removed = agent.remove_item_by_id(material_id, count)
            result["materials_consumed"][material_id] = removed
        
        # レシピ習得（簡易実装）
        from ..models.job import Recipe
        new_recipe = Recipe(
            recipe_id=learn_action.recipe_id,
            name=f"習得レシピ_{learn_action.recipe_id}",
            description="習得したレシピ",
            required_materials={"material": 1},
            produced_item_id="product",
            required_job_level=1
        )
        
        success = agent.learn_recipe(new_recipe)
        if success:
            result["success"] = True
            result["recipe_learned"] = new_recipe
            result["messages"].append(f"レシピ {learn_action.recipe_id} を習得しました")
            agent.add_job_experience(25)
        else:
            result["messages"].append("レシピの習得に失敗しました")
        
        return result
    
    def execute_agent_setup_shop(self, agent_id: str, shop_action: SetupShop) -> Dict:
        """店舗設営行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, MerchantAgent):
            raise ValueError(f"エージェント {agent_id} は商人ではありません")
        
        return agent.setup_shop(
            shop_action.shop_name,
            shop_action.shop_type,
            shop_action.offered_items,
            shop_action.offered_services
        )
    
    def execute_agent_provide_service(self, agent_id: str, service_action: ProvideService) -> Dict:
        """サービス提供行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, MerchantAgent):
            raise ValueError(f"エージェント {agent_id} は商人ではありません")
        
        if not service_action.is_valid(agent):
            raise ValueError("サービス提供条件を満たしていません")
        
        # 対象エージェントをチェック
        target_agent = self.get_agent(service_action.target_agent_id)
        if not target_agent:
            raise ValueError(f"対象エージェント {service_action.target_agent_id} が見つかりません")
        
        result = agent.provide_service(
            service_action.service_id,
            service_action.target_agent_id,
            service_action.custom_price
        )
        
        # 支払い処理
        if result["success"]:
            price = result["price_charged"]
            if target_agent.get_money() >= price:
                target_agent.add_money(-price)
                agent.add_money(price)
                result["messages"].append(f"{price}ゴールドが支払われました")
            else:
                result["success"] = False
                result["messages"].append("支払い能力が不足しています")
        
        return result
    
    def execute_agent_price_negotiation(self, agent_id: str, negotiation_action: PriceNegotiation) -> Dict:
        """価格交渉行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, MerchantAgent):
            raise ValueError(f"エージェント {agent_id} は商人ではありません")
        
        target_agent = self.get_agent(negotiation_action.target_agent_id)
        if not target_agent:
            raise ValueError(f"対象エージェント {negotiation_action.target_agent_id} が見つかりません")
        
        # 交渉結果を計算
        target_reputation = 1.0  # 簡易実装
        final_price = agent.negotiate_price(negotiation_action.original_price, target_reputation)
        
        result = {
            "success": True,
            "original_price": negotiation_action.original_price,
            "proposed_price": negotiation_action.proposed_price,
            "final_price": final_price,
            "negotiation_successful": final_price <= negotiation_action.proposed_price,
            "messages": [f"価格交渉の結果: {negotiation_action.original_price} → {final_price}ゴールド"]
        }
        
        # 経験値獲得
        agent.add_job_experience(5)
        
        return result
    
    def execute_agent_gather_resource(self, agent_id: str, gather_action: GatherResource) -> Dict:
        """資源採集行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, ProducerAgent):
            raise ValueError(f"エージェント {agent_id} は一次産業者ではありません")
        
        if not gather_action.is_valid(agent):
            raise ValueError("採集条件を満たしていません")
        
        return agent.gather_resource(
            gather_action.resource_type,
            gather_action.tool_item_id,
            gather_action.duration_minutes
        )
    
    def execute_agent_process_material(self, agent_id: str, process_action: ProcessMaterial) -> Dict:
        """材料加工行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, ProducerAgent):
            raise ValueError(f"エージェント {agent_id} は一次産業者ではありません")
        
        if not process_action.is_valid(agent):
            raise ValueError("加工条件を満たしていません")
        
        return agent.process_material(
            process_action.raw_material_id,
            process_action.processed_item_id,
            process_action.quantity
        )
    
    def execute_agent_manage_farm(self, agent_id: str, farm_action: ManageFarm) -> Dict:
        """農場管理行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, ProducerAgent):
            raise ValueError(f"エージェント {agent_id} は一次産業者ではありません")
        
        if not farm_action.is_valid(agent):
            raise ValueError("農場管理条件を満たしていません")
        
        # 簡易農場管理実装
        result = {
            "success": True,
            "farm_action": farm_action.farm_action,
            "crop_type": farm_action.crop_type,
            "plot_id": farm_action.plot_id,
            "experience_gained": 0,
            "items_produced": [],
            "messages": []
        }
        
        if farm_action.farm_action == "plant":
            if farm_action.seed_item_id:
                agent.remove_item_by_id(farm_action.seed_item_id, 1)
                result["messages"].append(f"{farm_action.crop_type}の種を植えました")
                agent.add_job_experience(5)
                result["experience_gained"] = 5
        elif farm_action.farm_action == "harvest":
            # 収穫物生成
            from ..models.item import Item
            harvest_item = Item(f"{farm_action.crop_type}_harvest", f"収穫した{farm_action.crop_type}")
            agent.add_item(harvest_item)
            result["items_produced"].append(harvest_item)
            result["messages"].append(f"{farm_action.crop_type}を収穫しました")
            agent.add_job_experience(10)
            result["experience_gained"] = 10
        elif farm_action.farm_action == "water":
            result["messages"].append(f"{farm_action.crop_type}に水をやりました")
            agent.add_job_experience(3)
            result["experience_gained"] = 3
        
        return result
    
    def execute_agent_advanced_combat(self, agent_id: str, combat_action: AdvancedCombat) -> Dict:
        """高度戦闘行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, AdventurerAgent):
            raise ValueError(f"エージェント {agent_id} は冒険者ではありません")
        
        if not combat_action.is_valid(agent):
            raise ValueError("戦闘スキル使用条件を満たしていません")
        
        return agent.use_combat_skill(combat_action.combat_skill, combat_action.target_id)
    
    # === 新しい商人システム関連の行動実行メソッド ===
    
    def execute_agent_sell_item(self, agent_id: str, sell_action: SellItem) -> Dict:
        """アイテム販売行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, TraderAgent):
            raise ValueError(f"エージェント {agent_id} は商人ではありません")
        
        if not sell_action.is_valid(agent):
            # デバッグ情報を追加
            item_count = agent.get_item_count(sell_action.item_id)
            raise ValueError(f"販売条件を満たしていません - アイテム: {sell_action.item_id}, 必要: {sell_action.quantity}, 所持: {item_count}")
        
        # 顧客エージェントを取得
        customer = self.get_agent(sell_action.customer_agent_id)
        if not customer:
            raise ValueError(f"顧客エージェント {sell_action.customer_agent_id} が見つかりません")
        
        # 同じスポットにいるかチェック
        if agent.get_current_spot_id() != customer.get_current_spot_id():
            raise ValueError("顧客と同じスポットにいません")
        
        # 顧客の支払い能力チェック
        total_price = sell_action.get_total_price()
        if customer.get_money() < total_price:
            return {
                "success": False,
                "message": f"顧客の資金不足: 必要{total_price}ゴールド、所持{customer.get_money()}ゴールド"
            }
        
        # 販売実行
        result = agent.sell_item_to_customer(
            sell_action.customer_agent_id,
            sell_action.item_id,
            sell_action.quantity,
            sell_action.price_per_item
        )
        
        if result["success"]:
            # 顧客にアイテムを転送し、支払いを処理
            from ..models.item import Item
            for _ in range(sell_action.quantity):
                item = Item(sell_action.item_id, f"{agent.name}から購入")
                customer.add_item(item)
            
            customer.add_money(-total_price)
            result["messages"].append(f"顧客に{total_price}ゴールドを請求しました")
        
        return result
    
    def execute_agent_buy_item(self, agent_id: str, buy_action: BuyItem) -> Dict:
        """アイテム購入行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, TraderAgent):
            raise ValueError(f"エージェント {agent_id} は商人ではありません")
        
        if not buy_action.is_valid(agent):
            raise ValueError("購入条件を満たしていません")
        
        # 顧客エージェントを取得
        customer = self.get_agent(buy_action.customer_agent_id)
        if not customer:
            raise ValueError(f"顧客エージェント {buy_action.customer_agent_id} が見つかりません")
        
        # 同じスポットにいるかチェック
        if agent.get_current_spot_id() != customer.get_current_spot_id():
            raise ValueError("顧客と同じスポットにいません")
        
        # 顧客のアイテム所持チェック
        if customer.get_item_count(buy_action.item_id) < buy_action.quantity:
            return {
                "success": False,
                "message": f"顧客のアイテム不足: {buy_action.item_id} x {buy_action.quantity}"
            }
        
        # 購入実行
        result = agent.buy_item_from_customer(
            buy_action.customer_agent_id,
            buy_action.item_id,
            buy_action.quantity,
            buy_action.price_per_item
        )
        
        if result["success"]:
            # 顧客からアイテムを受け取り、支払いを処理
            for _ in range(buy_action.quantity):
                customer.remove_item_by_id(buy_action.item_id, 1)
            
            total_price = buy_action.get_total_price()
            customer.add_money(total_price)
            result["messages"].append(f"顧客に{total_price}ゴールドを支払いました")
        
        return result
    
    def execute_agent_set_item_price(self, agent_id: str, price_action: SetItemPrice) -> Dict:
        """商品価格設定行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, TraderAgent):
            raise ValueError(f"エージェント {agent_id} は商人ではありません")
        
        if not price_action.is_valid(agent):
            raise ValueError("価格設定条件を満たしていません")
        
        return agent.set_item_price(price_action.item_id, price_action.price)
    
    def execute_agent_manage_inventory(self, agent_id: str, inventory_action: ManageInventory) -> Dict:
        """店舗在庫管理行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, TraderAgent):
            raise ValueError(f"エージェント {agent_id} は商人ではありません")
        
        if not inventory_action.is_valid(agent):
            raise ValueError("在庫管理条件を満たしていません")
        
        return agent.manage_shop_inventory(
            inventory_action.action_type,
            inventory_action.item_id,
            inventory_action.quantity
        )
    
    def execute_agent_provide_lodging(self, agent_id: str, lodging_action: ProvideLodging) -> Dict:
        """宿泊サービス提供行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, ServiceProviderAgent):
            raise ValueError(f"エージェント {agent_id} はサービス提供者ではありません")
        
        if not lodging_action.is_valid(agent):
            raise ValueError("宿泊サービス提供条件を満たしていません")
        
        # ゲストエージェントを取得
        guest = self.get_agent(lodging_action.guest_agent_id)
        if not guest:
            raise ValueError(f"ゲストエージェント {lodging_action.guest_agent_id} が見つかりません")
        
        # 同じスポットにいるかチェック
        if agent.get_current_spot_id() != guest.get_current_spot_id():
            raise ValueError("ゲストと同じスポットにいません")
        
        # ゲストの支払い能力チェック
        total_cost = lodging_action.get_total_price()
        if guest.get_money() < total_cost:
            return {
                "success": False,
                "message": f"ゲストの資金不足: 必要{total_cost}ゴールド、所持{guest.get_money()}ゴールド"
            }
        
        # 宿泊サービス実行
        result = agent.provide_lodging_service(
            lodging_action.guest_agent_id,
            lodging_action.nights,
            lodging_action.room_type
        )
        
        if result["success"]:
            # ゲストを一時的に宿屋スポットに移動（簡易実装）
            guest.original_spot_id = guest.get_current_spot_id()  # 元の場所を記録
            # 支払い処理
            guest.add_money(-total_cost)
            # HP/MP全回復効果を適用
            guest.set_hp(guest.max_hp)
            guest.set_mp(guest.max_mp)
            result["messages"].append(f"ゲストのHP/MPが全回復しました")
            result["messages"].append(f"ゲストが{total_cost}ゴールドを支払いました")
        
        return result
    
    def execute_agent_provide_dance(self, agent_id: str, dance_action: ProvideDance) -> Dict:
        """舞サービス提供行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, ServiceProviderAgent):
            raise ValueError(f"エージェント {agent_id} はサービス提供者ではありません")
        
        if not dance_action.is_valid(agent):
            raise ValueError("舞サービス提供条件を満たしていません")
        
        # 対象エージェントを取得
        target = self.get_agent(dance_action.target_agent_id)
        if not target:
            raise ValueError(f"対象エージェント {dance_action.target_agent_id} が見つかりません")
        
        # 同じスポットにいるかチェック
        if agent.get_current_spot_id() != target.get_current_spot_id():
            raise ValueError("対象と同じスポットにいません")
        
        # 対象の支払い能力チェック
        if target.get_money() < dance_action.price:
            return {
                "success": False,
                "message": f"対象の資金不足: 必要{dance_action.price}ゴールド、所持{target.get_money()}ゴールド"
            }
        
        # 舞サービス実行
        result = agent.provide_dance_service(dance_action.target_agent_id, dance_action.dance_type)
        
        if result["success"]:
            # 効果を対象に適用
            effects = result["effects"]
            if "mp_recovery" in effects:
                mp_recovery = effects["mp_recovery"]
                target.set_mp(min(target.max_mp, target.current_mp + mp_recovery))
                result["messages"].append(f"対象のMPが{mp_recovery}回復しました")
            
            # 支払い処理
            target.add_money(-result["price"])
            result["messages"].append(f"対象が{result['price']}ゴールドを支払いました")
        
        return result
    
    def execute_agent_provide_prayer(self, agent_id: str, prayer_action: ProvidePrayer) -> Dict:
        """祈祷サービス提供行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, ServiceProviderAgent):
            raise ValueError(f"エージェント {agent_id} はサービス提供者ではありません")
        
        if not prayer_action.is_valid(agent):
            raise ValueError("祈祷サービス提供条件を満たしていません")
        
        # 対象エージェントを取得
        target = self.get_agent(prayer_action.target_agent_id)
        if not target:
            raise ValueError(f"対象エージェント {prayer_action.target_agent_id} が見つかりません")
        
        # 同じスポットにいるかチェック
        if agent.get_current_spot_id() != target.get_current_spot_id():
            raise ValueError("対象と同じスポットにいません")
        
        # 対象の支払い能力チェック
        if target.get_money() < prayer_action.price:
            return {
                "success": False,
                "message": f"対象の資金不足: 必要{prayer_action.price}ゴールド、所持{target.get_money()}ゴールド"
            }
        
        # 祈祷サービス実行
        result = agent.provide_prayer_service(prayer_action.target_agent_id, prayer_action.prayer_type)
        
        if result["success"]:
            # 効果を対象に適用
            effects = result["effects"]
            if "hp_recovery" in effects:
                hp_recovery = effects["hp_recovery"]
                target.set_hp(min(target.max_hp, target.current_hp + hp_recovery))
                result["messages"].append(f"対象のHPが{hp_recovery}回復しました")
            
            if "mp_recovery" in effects:
                mp_recovery = effects["mp_recovery"]
                target.set_mp(min(target.max_mp, target.current_mp + mp_recovery))
                result["messages"].append(f"対象のMPが{mp_recovery}回復しました")
            
            # 支払い処理
            target.add_money(-result["price"])
            result["messages"].append(f"対象が{result['price']}ゴールドを支払いました")
        
        return result

    # === クエストシステム関連の行動実行メソッド ===
    
    def execute_agent_view_available_quests(self, agent_id: str, action: ViewAvailableQuests) -> Dict:
        """受注可能クエスト表示行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, AdventurerAgent):
            return {"success": False, "message": "冒険者のみクエストを受注できます"}
        
        quests = self.quest_system.get_available_quests(agent_id)
        quest_data = [quest.to_dict() for quest in quests]
        
        return {
            "success": True,
            "available_quests": quest_data,
            "count": len(quests)
        }
    
    def execute_agent_accept_quest(self, agent_id: str, action: AcceptQuest) -> Dict:
        """クエスト受注行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, AdventurerAgent):
            return {"success": False, "message": "冒険者のみクエストを受注できます"}
        
        if agent.has_active_quest():
            return {"success": False, "message": "既にアクティブなクエストがあります"}
        
        success = self.quest_system.accept_quest(agent_id, action.quest_id)
        if success:
            agent.accept_quest(action.quest_id)
            quest = self.quest_system.get_quest_by_id(action.quest_id)
            return {
                "success": True,
                "message": f"クエスト '{quest.name}' を受注しました",
                "quest": quest.to_dict() if quest else None
            }
        else:
            return {"success": False, "message": "クエストの受注に失敗しました"}
    
    def execute_agent_cancel_quest(self, agent_id: str, action: CancelQuest) -> Dict:
        """クエストキャンセル行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, AdventurerAgent):
            return {"success": False, "message": "冒険者のみクエストをキャンセルできます"}
        
        if not agent.has_active_quest():
            return {"success": False, "message": "アクティブなクエストがありません"}
        
        success = self.quest_system.cancel_quest(agent_id, action.quest_id)
        if success:
            agent.cancel_quest(action.quest_id)
            return {"success": True, "message": "クエストをキャンセルしました"}
        else:
            return {"success": False, "message": "クエストのキャンセルに失敗しました"}
    
    def execute_agent_view_quest_progress(self, agent_id: str, action: ViewQuestProgress) -> Dict:
        """クエスト進捗確認行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, AdventurerAgent):
            return {"success": False, "message": "冒険者のみクエスト進捗を確認できます"}
        
        quest = self.quest_system.get_active_quest(agent_id)
        if not quest:
            return {"success": False, "message": "アクティブなクエストがありません"}
        
        return {
            "success": True,
            "quest": quest.to_dict(),
            "progress": quest.get_progress_summary()
        }
    
    def execute_agent_submit_quest(self, agent_id: str, action: SubmitQuest) -> Dict:
        """クエスト提出行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, AdventurerAgent):
            return {"success": False, "message": "冒険者のみクエストを提出できます"}
        
        # クエスト完了チェックと報酬配布
        result = self.quest_system.check_quest_completion(agent_id)
        if not result:
            return {"success": False, "message": "完了可能なクエストがありません"}
        
        if result["success"]:
            # エージェントにも完了を記録
            agent.complete_quest(action.quest_id)
            
            # 報酬を配布
            agent.add_money(result["reward_money"])
            agent.add_experience_points(result["experience_gained"])
            
            return {
                "success": True,
                "message": result["message"],
                "reward_money": result["reward_money"],
                "guild_fee": result["guild_fee"],
                "experience_gained": result["experience_gained"],
                "reputation_gained": result["reputation_gained"]
            }
        else:
            return {"success": False, "message": result["message"]}
    
    def execute_agent_register_to_guild(self, agent_id: str, action: RegisterToGuild) -> Dict:
        """ギルド登録行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not isinstance(agent, AdventurerAgent):
            return {"success": False, "message": "冒険者のみギルドに登録できます"}
        
        # 既に別のギルドに所属していないかチェック
        current_guild = self.quest_system.get_agent_guild(agent_id)
        if current_guild:
            return {"success": False, "message": f"既に {current_guild.name} に所属しています"}
        
        success = self.quest_system.register_agent_to_guild(agent, action.guild_id)
        if success:
            guild = self.quest_system.get_guild(action.guild_id)
            return {
                "success": True,
                "message": f"ギルド '{guild.name}' に登録しました",
                "guild_info": guild.get_guild_stats()
            }
        else:
            return {"success": False, "message": "ギルド登録に失敗しました"}
    
    def execute_agent_post_quest_to_guild(self, agent_id: str, action: PostQuestToGuild) -> Dict:
        """ギルドへのクエスト依頼行動を実行"""
        agent = self.get_agent(agent_id)
        
        if not action.is_valid(agent):
            return {"success": False, "message": "依頼料が不足しています"}
        
        # クエストタイプに応じてクエストを生成
        quest_difficulty = QuestDifficulty(action.difficulty)
        
        if action.quest_type == "monster_hunt":
            quest = self.quest_system.create_monster_hunt_quest_for_guild(
                action.guild_id, action.quest_name, action.quest_description,
                action.target, action.target_count, quest_difficulty,
                agent_id, action.reward_money, action.deadline_hours
            )
        elif action.quest_type == "item_collection":
            quest = self.quest_system.create_item_collection_quest_for_guild(
                action.guild_id, action.quest_name, action.quest_description,
                action.target, action.target_count, quest_difficulty,
                agent_id, action.reward_money, action.deadline_hours
            )
        elif action.quest_type == "exploration":
            quest = self.quest_system.create_exploration_quest_for_guild(
                action.guild_id, action.quest_name, action.quest_description,
                action.target, quest_difficulty, agent_id,
                action.reward_money, action.deadline_hours
            )
        else:
            return {"success": False, "message": "不明なクエストタイプです"}
        
        # ギルドにクエストを依頼
        success = self.quest_system.post_quest_to_guild(action.guild_id, quest, agent)
        if success:
            return {
                "success": True,
                "message": f"クエスト '{quest.name}' をギルドに依頼しました",
                "quest": quest.to_dict()
            }
        else:
            return {"success": False, "message": "クエストの依頼に失敗しました"}
    
    # === クエスト進捗の自動更新 ===
    
    def _update_quest_progress_on_monster_kill(self, agent_id: str, monster_id: str):
        """モンスター討伐時のクエスト進捗更新"""
        quest = self.quest_system.handle_monster_kill(agent_id, monster_id)
        if quest:
            # クエストが完了したかチェック
            if quest.check_completion():
                # クエストを完了状態にする
                completion_result = self.quest_system.check_quest_completion(agent_id)
                if completion_result and completion_result["success"]:
                    agent = self.get_agent(agent_id)
                    # エージェントにも完了を記録
                    if hasattr(agent, 'complete_quest'):
                        agent.complete_quest(quest.quest_id)
                    agent.add_discovered_info(f"クエスト '{quest.name}' が完了しました！報酬を受け取りました。")
                else:
                    # 完了処理が既に実行済みの場合でも、エージェントには通知
                    agent = self.get_agent(agent_id)
                    if hasattr(agent, 'complete_quest'):
                        agent.complete_quest(quest.quest_id)
                    agent.add_discovered_info(f"クエスト '{quest.name}' が完了しました！")
    
    def _update_quest_progress_on_item_get(self, agent_id: str, item_id: str, count: int = 1):
        """アイテム取得時のクエスト進捗更新"""
        quest = self.quest_system.handle_item_collection(agent_id, item_id, count)
        if quest:
            # 完了チェック
            completion_result = self.quest_system.check_quest_completion(agent_id)
            if completion_result and completion_result["success"]:
                agent = self.get_agent(agent_id)
                agent.add_discovered_info(f"クエスト '{quest.name}' が完了しました！ギルドで報酬を受け取ってください。")
    
    def _update_quest_progress_on_location_visit(self, agent_id: str, spot_id: str):
        """場所訪問時のクエスト進捗更新"""
        quest = self.quest_system.handle_location_visit(agent_id, spot_id)
        if quest:
            # 完了チェック
            completion_result = self.quest_system.check_quest_completion(agent_id)
            if completion_result and completion_result["success"]:
                agent = self.get_agent(agent_id)
                agent.add_discovered_info(f"クエスト '{quest.name}' が完了しました！ギルドで報酬を受け取ってください。")
    
    # === 家システム関連メソッド ===
    
    def create_home(self, home_id: str, name: str, description: str, 
                   owner_agent_id: str, price: int = 0, parent_spot_id: Optional[str] = None) -> Home:
        """家を作成してワールドに追加"""
        home = Home(home_id, name, description, owner_agent_id, price, parent_spot_id)
        
        # 自動的に自分の部屋を作成
        bedroom_id = f"{home_id}_bedroom"
        bedroom = Spot(bedroom_id, f"{name}の寝室", "家の主人の寝室。ベッドと机がある。", home_id)
        
        # ベッドと机を追加
        bed = Bed(f"{bedroom_id}_bed", "ベッド", "快適そうなベッド。ゆっくりと休むことができそうだ。")
        desk = Desk(f"{bedroom_id}_desk", "机", "木製の机。日記や書類を書くのに適している。")
        
        bedroom.add_interactable(bed)
        bedroom.add_interactable(desk)
        
        # スポットとして追加
        self.add_spot(home)
        self.add_spot(bedroom)
        
        # 親子関係を設定
        home.add_child_spot(bedroom_id)
        home.add_entry_point("正面玄関", bedroom_id)
        bedroom.set_exit_to_parent(home_id)
        bedroom.set_as_entrance("正面玄関")
        
        # 価格を更新
        home.update_price()
        
        return home
    
    def execute_agent_write_diary(self, agent_id: str, action: WriteDiary) -> Dict[str, Any]:
        """日記記入行動を実行"""
        agent = self.get_agent(agent_id)
        current_spot = self.get_spot(agent.get_current_spot_id())
        
        # 現在の場所が家かどうかチェック
        if isinstance(current_spot, Home):
            home = current_spot
        else:
            # 親スポットが家かどうかチェック
            parent_spot_id = current_spot.get_parent_spot_id()
            if parent_spot_id and isinstance(self.get_spot(parent_spot_id), Home):
                home = self.get_spot(parent_spot_id)
            else:
                return {"success": False, "message": "家の中でのみ日記を書くことができます。"}
        
        # 権限チェック
        if not home.has_owner_permission(agent_id):
            return {"success": False, "message": "この家で日記を書く権限がありません。"}
        
        # 日記エントリを追加
        success = home.add_diary_entry(agent_id, action.content, action.date)
        
        if success:
            agent.add_experience_points(3)
            return {
                "success": True, 
                "message": f"日記を書きました: {action.content[:50]}{'...' if len(action.content) > 50 else ''}"
            }
        else:
            return {"success": False, "message": "日記の記入に失敗しました。"}
    
    def execute_agent_read_diary(self, agent_id: str, action: ReadDiary) -> Dict[str, Any]:
        """日記読み取り行動を実行"""
        agent = self.get_agent(agent_id)
        current_spot = self.get_spot(agent.get_current_spot_id())
        
        # 現在の場所が家かどうかチェック
        if isinstance(current_spot, Home):
            home = current_spot
        else:
            # 親スポットが家かどうかチェック
            parent_spot_id = current_spot.get_parent_spot_id()
            if parent_spot_id and isinstance(self.get_spot(parent_spot_id), Home):
                home = self.get_spot(parent_spot_id)
            else:
                return {"success": False, "message": "家の中でのみ日記を読むことができます。"}
        
        # 権限チェック
        if not home.has_visitor_permission(agent_id):
            return {"success": False, "message": "この家で日記を読む権限がありません。"}
        
        # 日記エントリを取得
        entries = home.get_diary_entries(agent_id)
        
        if not entries:
            return {"success": True, "message": "日記にはまだ何も書かれていません。", "entries": []}
        
        # 特定の日付が指定されている場合
        if action.target_date:
            entries = [entry for entry in entries if entry["date"] == action.target_date]
            if not entries:
                return {
                    "success": True, 
                    "message": f"{action.target_date}の日記は見つかりませんでした。", 
                    "entries": []
                }
        
        agent.add_experience_points(1)
        return {
            "success": True, 
            "message": f"{len(entries)}件の日記エントリを読みました。",
            "entries": entries
        }
    
    def execute_agent_sleep(self, agent_id: str, action: Sleep) -> Dict[str, Any]:
        """睡眠行動を実行"""
        agent = self.get_agent(agent_id)
        current_spot = self.get_spot(agent.get_current_spot_id())
        
        # 現在の場所が家かどうかチェック
        if isinstance(current_spot, Home):
            home = current_spot
        else:
            # 親スポットが家かどうかチェック
            parent_spot_id = current_spot.get_parent_spot_id()
            if parent_spot_id and isinstance(self.get_spot(parent_spot_id), Home):
                home = self.get_spot(parent_spot_id)
            else:
                return {"success": False, "message": "家の中でのみ睡眠できます。"}
        
        # 権限チェック
        if not home.has_owner_permission(agent_id):
            return {"success": False, "message": "この家で睡眠する権限がありません。"}
        
        # ベッドを探す
        bed = None
        for interactable in current_spot.get_all_interactables():
            if isinstance(interactable, Bed):
                bed = interactable
                break
        
        if not bed:
            return {"success": False, "message": "この場所にはベッドがありません。"}
        
        # 睡眠実行
        success = bed.sleep(agent)
        
        if success:
            agent.add_experience_points(5)
            return {
                "success": True, 
                "message": f"ゆっくりと{action.duration}時間眠りました。体力と魔力が全回復しました。",
                "hp_recovered": agent.max_hp - agent.current_hp,
                "mp_recovered": agent.max_mp - agent.current_mp
            }
        else:
            return {"success": False, "message": "ベッドが使用中です。"}
    
    def execute_agent_grant_home_permission(self, agent_id: str, action: GrantHomePermission) -> Dict[str, Any]:
        """家の権限付与行動を実行"""
        agent = self.get_agent(agent_id)
        current_spot = self.get_spot(agent.get_current_spot_id())
        
        # 現在の場所が家かどうかチェック
        if isinstance(current_spot, Home):
            home = current_spot
        else:
            # 親スポットが家かどうかチェック
            parent_spot_id = current_spot.get_parent_spot_id()
            if parent_spot_id and isinstance(self.get_spot(parent_spot_id), Home):
                home = self.get_spot(parent_spot_id)
            else:
                return {"success": False, "message": "家の中でのみ権限を付与できます。"}
        
        # 所有者権限チェック
        if not home.has_owner_permission(agent_id):
            return {"success": False, "message": "権限を付与する権限がありません。"}
        
        # 対象エージェントの存在チェック
        if action.target_agent_id not in self.agents:
            return {"success": False, "message": "指定されたエージェントが見つかりません。"}
        
        # 権限設定
        if action.permission_level == "visitor":
            permission = HomePermission.VISITOR
        elif action.permission_level == "owner":
            permission = HomePermission.OWNER
        else:
            return {"success": False, "message": "無効な権限レベルです。"}
        
        home.set_permission(action.target_agent_id, permission)
        target_agent = self.get_agent(action.target_agent_id)
        
        return {
            "success": True, 
            "message": f"{target_agent.name}に{action.permission_level}権限を付与しました。"
        }
    
    def execute_agent_store_item(self, agent_id: str, action: StoreItem) -> Dict[str, Any]:
        """アイテム保管行動を実行"""
        agent = self.get_agent(agent_id)
        current_spot = self.get_spot(agent.get_current_spot_id())
        
        # 現在の場所が家かどうかチェック
        if isinstance(current_spot, Home):
            home = current_spot
        else:
            # 親スポットが家かどうかチェック
            parent_spot_id = current_spot.get_parent_spot_id()
            if parent_spot_id and isinstance(self.get_spot(parent_spot_id), Home):
                home = self.get_spot(parent_spot_id)
            else:
                return {"success": False, "message": "家の中でのみアイテムを保管できます。"}
        
        # 権限チェック
        if not home.has_owner_permission(agent_id):
            return {"success": False, "message": "この家でアイテムを保管する権限がありません。"}
        
        # アイテムの所持チェック
        item = agent.get_item_by_id(action.item_id)
        if not item:
            return {"success": False, "message": "指定されたアイテムを所持していません。"}
        
        # アイテムをエージェントから削除し、家に保管
        agent.remove_item(item)
        success = home.store_item(agent_id, item)
        
        if success:
            return {"success": True, "message": f"{item.item_id}を家に保管しました。"}
        else:
            # 失敗した場合はアイテムを戻す
            agent.add_item(item)
            return {"success": False, "message": "アイテムの保管に失敗しました。"}
    
    def execute_agent_retrieve_item(self, agent_id: str, action: RetrieveItem) -> Dict[str, Any]:
        """アイテム取得行動を実行"""
        agent = self.get_agent(agent_id)
        current_spot = self.get_spot(agent.get_current_spot_id())
        
        # 現在の場所が家かどうかチェック
        if isinstance(current_spot, Home):
            home = current_spot
        else:
            # 親スポットが家かどうかチェック
            parent_spot_id = current_spot.get_parent_spot_id()
            if parent_spot_id and isinstance(self.get_spot(parent_spot_id), Home):
                home = self.get_spot(parent_spot_id)
            else:
                return {"success": False, "message": "家の中でのみアイテムを取得できます。"}
        
        # 権限チェック
        if not home.has_owner_permission(agent_id):
            return {"success": False, "message": "この家でアイテムを取得する権限がありません。"}
        
        # 保管されたアイテムから検索
        stored_items = home.get_stored_items(agent_id)
        target_item = None
        for item in stored_items:
            if item.item_id == action.item_id:
                target_item = item
                break
        
        if not target_item:
            return {"success": False, "message": "指定されたアイテムは保管されていません。"}
        
        # アイテムを家から削除し、エージェントに追加
        success = home.retrieve_item(agent_id, target_item)
        if success:
            agent.add_item(target_item)
            return {"success": True, "message": f"{target_item.item_id}を家から取得しました。"}
        else:
            return {"success": False, "message": "アイテムの取得に失敗しました。"}