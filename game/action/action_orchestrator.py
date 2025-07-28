from typing import List, Dict, Any
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
from game.action.action_result import ActionResult, ErrorActionResult


class ActionOrchestrator:
    def __init__(self, game_context: GameContext):
        self.game_context = game_context
        
        # グローバルアクション（場所に依存しない）
        self.global_strategies: Dict[str, ActionStrategy] = {
            MovementStrategy().get_name(): MovementStrategy(),
            UseItemStrategy().get_name(): UseItemStrategy(),
            PreviewItemEffectStrategy().get_name(): PreviewItemEffectStrategy(),
            EquipmentSetCheckStrategy().get_name(): EquipmentSetCheckStrategy(),
            EquipItemStrategy().get_name(): EquipItemStrategy(),
            UnequipItemStrategy().get_name(): UnequipItemStrategy(),
            InventoryCheckStrategy().get_name(): InventoryCheckStrategy(),
            ExploreActionStrategy().get_name(): ExploreActionStrategy(),
            SnsGetUserInfoStrategy().get_name(): SnsGetUserInfoStrategy(),
            SnsUpdateUserBioStrategy().get_name(): SnsUpdateUserBioStrategy(),
            SnsPostStrategy().get_name(): SnsPostStrategy(),
            SnsGetTimelineStrategy().get_name(): SnsGetTimelineStrategy(),
            SnsLikeStrategy().get_name(): SnsLikeStrategy(),
            SnsUnlikeStrategy().get_name(): SnsUnlikeStrategy(),
            SnsReplyStrategy().get_name(): SnsReplyStrategy(),
            SnsGetNotificationsStrategy().get_name(): SnsGetNotificationsStrategy(),
            SnsMarkNotificationReadStrategy().get_name(): SnsMarkNotificationReadStrategy(),
            QuestGetGuildListStrategy().get_name(): QuestGetGuildListStrategy(),
            QuestCreateMonsterHuntStrategy().get_name(): QuestCreateMonsterHuntStrategy(),
            QuestCreateItemCollectionStrategy().get_name(): QuestCreateItemCollectionStrategy(),
            QuestCreateExplorationStrategy().get_name(): QuestCreateExplorationStrategy(),
            QuestGetAvailableQuestsStrategy().get_name(): QuestGetAvailableQuestsStrategy(),
            QuestAcceptQuestStrategy().get_name(): QuestAcceptQuestStrategy(),
            QuestGetActiveQuestStrategy().get_name(): QuestGetActiveQuestStrategy(),
        }

    def get_action_candidates_for_llm(self, acting_player_id: str) -> List[Dict[str, Any]]:
        """
        LLMが行動選択を行うための候補アクションを取得
        新しいArgumentInfo構造に対応した形式で返す
        """
        acting_player = self.game_context.get_player_manager().get_player(acting_player_id)
        if not acting_player: 
            return []

        current_spot_id = acting_player.get_current_spot_id()
        spot_manager = self.game_context.get_spot_manager()
        current_spot = spot_manager.get_spot(current_spot_id)

        if not current_spot: 
            return []

        # スポット固有のアクションを取得
        possible_actions_at_spot = current_spot.get_possible_actions()
        
        candidates = []
        
        # スポット固有のアクションを処理
        for strategy in possible_actions_at_spot.values():
            if strategy.can_execute(acting_player, self.game_context):
                required_arguments = strategy.get_required_arguments(acting_player, self.game_context)
                candidates.append({
                    'action_name': strategy.get_name(),
                    'action_description': self._get_action_description(strategy.get_name()),
                    'required_arguments': self._format_arguments_for_llm(required_arguments),
                    'action_type': 'spot_specific'
                })
        
        # グローバルアクションを処理
        for strategy in self.global_strategies.values():
            if strategy.can_execute(acting_player, self.game_context):
                required_arguments = strategy.get_required_arguments(acting_player, self.game_context)
                candidates.append({
                    'action_name': strategy.get_name(),
                    'action_description': self._get_action_description(strategy.get_name()),
                    'required_arguments': self._format_arguments_for_llm(required_arguments),
                    'action_type': 'global'
                })
        
        return candidates

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
        }
        return descriptions.get(action_name, f"{action_name}を実行します")

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

        # スポット固有のアクションとグローバルアクションを統合
        possible_actions_at_spot = current_spot.get_possible_actions()
        all_available_actions = {**possible_actions_at_spot, **self.global_strategies}
    
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
        
        help_info = {
            'available_actions_count': len(candidates),
            'action_types': {
                'spot_specific': len([c for c in candidates if c['action_type'] == 'spot_specific']),
                'global': len([c for c in candidates if c['action_type'] == 'global'])
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
        
        return help_info