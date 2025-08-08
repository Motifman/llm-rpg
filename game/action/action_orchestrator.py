from typing import List, Dict, Any, Union
from game.core.game_context import GameContext
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.action.actions.move_action import MovementStrategy
from game.action.actions.item_action import UseItemStrategy, PreviewItemEffectStrategy
from game.action.actions.equipment_action import EquipmentSetCheckStrategy, EquipItemStrategy, UnequipItemStrategy
from game.action.actions.inventory_action import InventoryCheckStrategy
from game.action.actions.explore_action import ExploreActionStrategy
from game.action.actions.sns_action import (
    SnsGetUserInfoStrategy, SnsUpdateUserBioStrategy, SnsPostStrategy, 
    SnsGetTimelineStrategy, SnsLikeStrategy, SnsUnlikeStrategy, 
    SnsReplyStrategy, SnsGetNotificationsStrategy, SnsMarkNotificationReadStrategy
)
from game.action.actions.quest_action import (
    QuestGetGuildListStrategy, QuestCreateMonsterHuntStrategy, QuestCreateItemCollectionStrategy,
    QuestCreateExplorationStrategy, QuestGetAvailableQuestsStrategy, QuestAcceptQuestStrategy,
    QuestGetActiveQuestStrategy
)
from game.action.actions.sns_action import SnsOpenStrategy, SnsCloseStrategy
from game.action.actions.state_transition_action import (
    TradingOpenStrategy, TradingCloseStrategy, ConversationLeaveStrategy
)
from game.action.actions.battle_action import BattleStartStrategy, BattleJoinStrategy, BattleActionStrategy
from game.action.actions.conversation_action import (
    StartSpotConversationStrategy, StartPrivateConversationStrategy, 
    JoinSpotConversationStrategy, SpeakInConversationStrategy
)
from game.action.actions.trade_action import (
    PostTradeStrategy, AcceptTradeStrategy, CancelTradeStrategy, GetAvailableTradesStrategy
)
from game.enums import PlayerState
from game.action.candidates import ActionCandidates, ActionCandidate, ActionArgument
from game.action.action_result import ActionResult, ErrorActionResult


class ActionOrchestrator:
    def __init__(self, game_context: GameContext):
        self.game_context = game_context
        
        # 状態別の行動を定義
        self._initialize_state_strategies()

    def _initialize_state_strategies(self):
        """状態別の行動戦略を初期化"""
        
        # 通常状態で利用可能な行動
        self.normal_state_strategies: Dict[str, ActionStrategy] = {
            # 基本行動
            MovementStrategy().get_name(): MovementStrategy(),
            UseItemStrategy().get_name(): UseItemStrategy(),
            PreviewItemEffectStrategy().get_name(): PreviewItemEffectStrategy(),
            EquipmentSetCheckStrategy().get_name(): EquipmentSetCheckStrategy(),
            EquipItemStrategy().get_name(): EquipItemStrategy(),
            UnequipItemStrategy().get_name(): UnequipItemStrategy(),
            InventoryCheckStrategy().get_name(): InventoryCheckStrategy(),
            ExploreActionStrategy().get_name(): ExploreActionStrategy(),
            
            # 状態遷移行動
            SnsOpenStrategy().get_name(): SnsOpenStrategy(),
            TradingOpenStrategy().get_name(): TradingOpenStrategy(),
            StartSpotConversationStrategy().get_name(): StartSpotConversationStrategy(),
            StartPrivateConversationStrategy().get_name(): StartPrivateConversationStrategy(),
            JoinSpotConversationStrategy().get_name(): JoinSpotConversationStrategy(),
            BattleStartStrategy().get_name(): BattleStartStrategy(),
            BattleJoinStrategy().get_name(): BattleJoinStrategy(),
        }
        
        # 会話状態で利用可能な行動
        self.conversation_state_strategies: Dict[str, ActionStrategy] = {
            SpeakInConversationStrategy().get_name(): SpeakInConversationStrategy(),
            ConversationLeaveStrategy().get_name(): ConversationLeaveStrategy(),
        }
        
        # SNS状態で利用可能な行動
        self.sns_state_strategies: Dict[str, ActionStrategy] = {
            SnsGetUserInfoStrategy().get_name(): SnsGetUserInfoStrategy(),
            SnsUpdateUserBioStrategy().get_name(): SnsUpdateUserBioStrategy(),
            SnsPostStrategy().get_name(): SnsPostStrategy(),
            SnsGetTimelineStrategy().get_name(): SnsGetTimelineStrategy(),
            SnsLikeStrategy().get_name(): SnsLikeStrategy(),
            SnsUnlikeStrategy().get_name(): SnsUnlikeStrategy(),
            SnsReplyStrategy().get_name(): SnsReplyStrategy(),
            SnsGetNotificationsStrategy().get_name(): SnsGetNotificationsStrategy(),
            SnsMarkNotificationReadStrategy().get_name(): SnsMarkNotificationReadStrategy(),
            SnsCloseStrategy().get_name(): SnsCloseStrategy(),
        }
   
        # 戦闘状態で利用可能な行動
        self.battle_state_strategies: Dict[str, ActionStrategy] = {
            BattleActionStrategy().get_name(): BattleActionStrategy(),
        }
        
        # 取引状態で利用可能な行動
        self.trading_state_strategies: Dict[str, ActionStrategy] = {
            PostTradeStrategy().get_name(): PostTradeStrategy(),
            AcceptTradeStrategy().get_name(): AcceptTradeStrategy(),
            CancelTradeStrategy().get_name(): CancelTradeStrategy(),
            GetAvailableTradesStrategy().get_name(): GetAvailableTradesStrategy(),
            TradingCloseStrategy().get_name(): TradingCloseStrategy(),
        }

    def get_action_candidates_for_llm(self, acting_player_id: str) -> ActionCandidates:
        """
        LLMが行動選択を行うための候補アクションを取得
        プレイヤーの状態に応じて行動を提案する
        """
        acting_player = self.game_context.get_player_manager().get_player(acting_player_id)
        if not acting_player: 
            return ActionCandidates(items=[])

        current_spot_id = acting_player.get_current_spot_id()
        spot_manager = self.game_context.get_spot_manager()
        current_spot = spot_manager.get_spot(current_spot_id)

        if not current_spot: 
            return ActionCandidates(items=[])

        candidates: List[ActionCandidate] = []
        
        # プレイヤーの状態に応じて利用可能な行動を取得
        available_strategies = self._get_strategies_for_player_state(acting_player.get_player_state())
        
        # 状態に応じた行動を処理
        for strategy in available_strategies.values():
            if strategy.can_execute(acting_player, self.game_context):
                required_arguments = strategy.get_required_arguments(acting_player, self.game_context)
                candidates.append(ActionCandidate(
                    action_name=strategy.get_name(),
                    action_description=self._get_action_description(strategy.get_name()),
                    required_arguments=[
                        ActionArgument(
                            name=a['name'], description=a['description'], type=a['type'], candidates=a.get('candidates', [])
                        ) for a in self._format_arguments_for_llm(required_arguments)
                    ],
                    action_type='state_specific',
                    player_state=acting_player.get_player_state().value,
                ))
        
        # 通常状態の場合のみスポット固有のアクションを追加
        # （クエスト関連は将来Spot固有として実装予定のため除外）
        if acting_player.is_in_normal_state():
            possible_actions_at_spot = current_spot.get_possible_actions()
            for strategy in possible_actions_at_spot.values():
                # クエスト関連の行動は除外
                if not strategy.get_name().startswith("クエスト"):
                    if strategy.can_execute(acting_player, self.game_context):
                        required_arguments = strategy.get_required_arguments(acting_player, self.game_context)
                        candidates.append(ActionCandidate(
                            action_name=strategy.get_name(),
                            action_description=self._get_action_description(strategy.get_name()),
                            required_arguments=[
                                ActionArgument(
                                    name=a['name'], description=a['description'], type=a['type'], candidates=a.get('candidates', [])
                                ) for a in self._format_arguments_for_llm(required_arguments)
                            ],
                            action_type='spot_specific',
                        ))
        
        return ActionCandidates(items=candidates)

    def _get_strategies_for_player_state(self, player_state: PlayerState) -> Dict[str, ActionStrategy]:
        """プレイヤーの状態に応じた行動戦略を取得"""
        if player_state == PlayerState.NORMAL:
            return self.normal_state_strategies
        elif player_state == PlayerState.CONVERSATION:
            return self.conversation_state_strategies
        elif player_state == PlayerState.SNS:
            return self.sns_state_strategies
        elif player_state == PlayerState.BATTLE:
            return self.battle_state_strategies
        elif player_state == PlayerState.TRADING:
            return self.trading_state_strategies
        else:
            return {}

    def _format_arguments_for_llm(self, argument_infos: List[ArgumentInfo]) -> List[Dict[str, Any]]:
        """
        ArgumentInfoリストをLLMが理解しやすい形式に変換
        """
        formatted_args = []
        for arg_info in argument_infos:
            formatted_arg = {
                'name': arg_info.name,
                'description': arg_info.description,
                'type': 'choice' if arg_info.candidates else 'free_input',
            }
            
            if arg_info.candidates:
                formatted_arg['candidates'] = arg_info.candidates
            else:
                formatted_arg['candidates'] = []
            
            formatted_args.append(formatted_arg)
        
        return formatted_args

    def _get_action_description(self, action_name: str) -> str:
        """
        アクション名に対応する説明を返す
        """
        descriptions = {
            "移動": "他の場所に移動します",
            "消費アイテムの使用": "所持している消費アイテムを使用します",
            "アイテム効果の確認": "アイテムの効果を確認します",
            "装備確認": "現在の装備状況を確認します",
            "装備変更": "アイテムを装備します",
            "装備解除": "装備を外します",
            "所持アイテム確認": "所持アイテムを確認します",
            "探索": "現在の場所を探索します",
            "SNSユーザー情報取得": "SNSユーザーの情報を取得します",
            "SNSユーザー情報更新": "SNSユーザーの一言コメントを更新します",
            "SNS投稿": "SNSに投稿を作成します",
            "SNSタイムライン取得": "SNSのタイムラインを取得します",
            "SNS投稿にいいね": "SNS投稿にいいねします",
            "SNS投稿のいいね解除": "SNS投稿のいいねを解除します",
            "SNS投稿に返信": "SNS投稿に返信します",
            "SNS通知取得": "SNSの通知を取得します",
            "SNS通知を既読にする": "SNSの通知を既読にします",
            "ギルド一覧確認": "利用可能なギルドの一覧を確認します",
            "モンスタークエスト依頼": "モンスター討伐クエストをギルドに依頼します",
            "アイテムクエスト依頼": "アイテム収集クエストをギルドに依頼します",
            "探索クエスト依頼": "探索クエストをギルドに依頼します",
            "利用可能クエスト取得": "受注可能なクエストの一覧を取得します",
            "クエスト受注": "利用可能なクエストを受注します",
            "アクティブクエスト取得": "現在進行中のクエストを確認します",
            "宝箱を開ける": "宝箱を開けてアイテムを入手します",
            "掲示板に書き込む": "掲示板に投稿を書き込みます",
            "掲示板を読む": "掲示板の投稿を読みます",
            "石碑を読む": "石碑の内容を読みます",
            "SNSを開く": "SNSアプリケーションを開きます",
            "SNSを閉じる": "SNSアプリケーションを閉じます",
            "取引所を開く": "取引所を開きます",
            "取引所を閉じる": "取引所を閉じます",
            "会話を離脱する": "現在の会話から離脱します",
            "戦闘開始": "モンスターとの戦闘を開始します",
            "戦闘に参加": "進行中の戦闘に参加します",
            "戦闘時の行動": "戦闘中に行動を実行します",
            "スポット会話開始": "現在の場所で会話を開始します",
            "個人会話開始": "特定のプレイヤーと個人会話を開始します",
            "スポット会話参加": "進行中の会話に参加します",
            "会話発言": "会話中に発言します",
            "取引出品": "アイテムを取引に出品します",
            "取引受託": "出品された取引を受託します",
            "取引キャンセル": "自分が出品した取引をキャンセルします",
            "受託可能取引取得": "現在受託可能な取引一覧を取得します",
        }
        return descriptions.get(action_name, "未知のアクションを実行します")

    def execute_llm_action(self, acting_player_id: str, action_name: str, action_args: dict) -> ActionResult:
        """
        LLMが選択したアクションを実行
        """
        acting_player = self.game_context.get_player_manager().get_player(acting_player_id)
        
        if not acting_player:
            return ErrorActionResult(f"プレイヤー {acting_player_id} が見つかりません。")
        
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = self.game_context.get_spot_manager().get_spot(current_spot_id)

        if not current_spot: 
            return ErrorActionResult(f"プレイヤー {acting_player_id} の現在地が見つかりません。")

        # プレイヤーの状態に応じた行動とスポット固有のアクションを統合
        available_strategies = self._get_strategies_for_player_state(acting_player.get_player_state())
        possible_actions_at_spot = current_spot.get_possible_actions()
        all_available_actions = {**available_strategies, **possible_actions_at_spot}
    
        strategy = all_available_actions.get(action_name)
        if not strategy:
            return ErrorActionResult(f"不明な行動名: {action_name}")
        
        if not strategy.can_execute(acting_player, self.game_context):
            return ErrorActionResult(f"{acting_player.name} は {action_name} を実行できません。現在の状態では不可能です。")

        try:
            command = strategy.build_action_command(acting_player, self.game_context, **action_args)
            result = command.execute(acting_player, self.game_context)
            return result
        except ValueError as e:
            return ErrorActionResult(f"行動の引数エラー: {e}")
        except Exception as e:
            return ErrorActionResult(f"行動実行中に予期せぬエラーが発生しました: {e}")

    def get_action_help_for_llm(self, acting_player_id: str) -> Dict[str, Any]:
        """
        LLMが行動選択を行う際のヘルプ情報を提供
        """
        candidates = self.get_action_candidates_for_llm(acting_player_id)
        return self.build_action_help_from_candidates(candidates)

    def build_action_help_from_candidates(self, candidates: Union[ActionCandidates, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """すでに生成済みの候補からヘルプ情報を構築する（候補の再生成を避ける）。"""
        # 統一のため辞書リストへ正規化
        if isinstance(candidates, ActionCandidates):
            cand_dicts = candidates.to_dicts()
        else:
            cand_dicts = candidates
        return {
            'available_actions_count': len(cand_dicts),
            'action_types': {
                'spot_specific': len([c for c in cand_dicts if c.get('action_type') == 'spot_specific']),
                'state_specific': len([c for c in cand_dicts if c.get('action_type') == 'state_specific'])
            },
            'usage_instructions': {
                'action_selection': '利用可能なアクションから1つを選択してください',
                'argument_format': '各アクションのrequired_argumentsに従って引数を指定してください',
                'argument_types': {
                    'choice': '候補リストから選択してください',
                    'free_input': '自由に入力してください'
                }
            }
        }