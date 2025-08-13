import pytest
from game.action.action_orchestrator import ActionOrchestrator
from game.core.game_context import GameContext
from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.world.spot import Spot
from game.player.player import Player
from game.enums import Role
from game.object.chest import Chest
from game.object.bulletin_board import BulletinBoard
from game.object.monument import Monument


class TestActionOrchestrator:
    def setup_method(self):
        """テスト前のセットアップ"""
        self.player_manager = PlayerManager()
        self.spot_manager = SpotManager()
        self.game_context = GameContext(self.player_manager, self.spot_manager)
        self.orchestrator = ActionOrchestrator(self.game_context)
        
        # テスト用プレイヤーを作成
        self.player = Player("test_player", "テストプレイヤー", Role.CITIZEN)
        self.player_manager.add_player(self.player)
        
        # テスト用スポットを作成
        self.spot = Spot("test_spot", "テストスポット", "テスト用の場所")
        self.spot2 = Spot("test_spot2", "テストスポット2", "テスト用の場所2")
        self.spot_manager.add_spot(self.spot)
        self.spot_manager.add_spot(self.spot2)
        
        # スポット間の接続を追加
        self.spot_manager.get_movement_graph().add_connection("test_spot", "test_spot2", "テスト接続")
        self.spot_manager.get_movement_graph().add_connection("test_spot2", "test_spot", "テスト接続")
        
        self.player.set_current_spot_id("test_spot")

    def test_action_orchestrator_initialization(self):
        """ActionOrchestratorの初期化テスト"""
        assert self.orchestrator.game_context == self.game_context
        # 状態ベースの設計に合わせ、候補を経由して確認
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        action_names = [c['action_name'] for c in candidates]
        assert "移動" in action_names
        assert "所持アイテム確認" in action_names

    def test_get_action_candidates_for_llm_basic(self):
        """基本的なアクション候補取得テスト"""
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        
        # 型はリスト互換のコンテナ（ActionCandidates）
        assert hasattr(candidates, "__iter__")
        assert len(candidates) > 0
        
        # グローバルアクションが含まれていることを確認
        action_names = [c['action_name'] for c in candidates]
        assert "移動" in action_names
        assert "所持アイテム確認" in action_names

    def test_get_action_candidates_for_llm_with_spot_actions(self):
        """スポット固有アクションを含む候補取得テスト"""
        # スポットに宝箱を追加
        chest = Chest("test_chest", "テスト宝箱")
        self.spot.add_interactable(chest)
        
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        
        # 宝箱を開けるアクションが含まれていることを確認
        action_names = [c['action_name'] for c in candidates]
        assert "宝箱を開ける" in action_names
        
        # 宝箱を開けるアクションの詳細を確認
        chest_action = next(c for c in candidates if c['action_name'] == "宝箱を開ける")
        assert chest_action['action_type'] == 'spot_specific'
        assert chest_action['action_description'] == "宝箱を開けてアイテムを入手します"
        assert len(chest_action['required_arguments']) == 1
        assert chest_action['required_arguments'][0]['name'] == 'chest_name'

    def test_get_action_candidates_for_llm_with_bulletin_board(self):
        """掲示板アクションを含む候補取得テスト"""
        # スポットに掲示板を追加
        board = BulletinBoard("test_board", "テスト掲示板")
        self.spot.add_interactable(board)
        
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        
        # 掲示板関連のアクションが含まれていることを確認
        action_names = [c['action_name'] for c in candidates]
        assert "掲示板に書き込む" in action_names
        assert "掲示板を読む" in action_names
        
        # 掲示板に書き込むアクションの詳細を確認
        write_action = next(c for c in candidates if c['action_name'] == "掲示板に書き込む")
        assert write_action['action_type'] == 'spot_specific'
        assert len(write_action['required_arguments']) == 2
        assert write_action['required_arguments'][0]['name'] == 'board_name'
        assert write_action['required_arguments'][1]['name'] == 'content'

    def test_format_arguments_for_llm(self):
        """LLM用引数フォーマットテスト"""
        from game.action.action_strategy import ArgumentInfo
        
        # テスト用のArgumentInfoリストを作成
        test_args = [
            ArgumentInfo("test_arg", "テスト引数", ["option1", "option2"]),
            ArgumentInfo("free_arg", "自由入力引数", None)
        ]
        
        formatted = self.orchestrator._format_arguments_for_llm(test_args)
        
        assert len(formatted) == 2
        
        # 選択型引数の確認
        choice_arg = formatted[0]
        assert choice_arg['name'] == 'test_arg'
        assert choice_arg['description'] == 'テスト引数'
        assert choice_arg['type'] == 'choice'
        assert choice_arg['candidates'] == ["option1", "option2"]
        
        # 自由入力型引数の確認
        free_arg = formatted[1]
        assert free_arg['name'] == 'free_arg'
        assert free_arg['description'] == '自由入力引数'
        assert free_arg['type'] == 'free_input'
        assert free_arg['candidates'] == []

    def test_get_action_description(self):
        """アクション説明取得テスト"""
        description = self.orchestrator._get_action_description("移動")
        assert description == "他の場所に移動します"
        
        description = self.orchestrator._get_action_description("未知のアクション")
        assert description == "未知のアクションを実行します"

    def test_execute_llm_action_success(self):
        """LLMアクション実行成功テスト"""
        # 移動アクションを実行
        result = self.orchestrator.execute_llm_action(
            "test_player", 
            "移動", 
            {"target_spot_id": "test_spot2"}
        )
        
        assert result.success == True

    def test_execute_llm_action_invalid_action(self):
        """無効なアクション実行テスト"""
        result = self.orchestrator.execute_llm_action(
            "test_player", 
            "存在しないアクション", 
            {}
        )
        
        assert result.success == False
        assert "不明な行動名" in result.message

    def test_execute_llm_action_invalid_player(self):
        """無効なプレイヤーでのアクション実行テスト"""
        result = self.orchestrator.execute_llm_action(
            "存在しないプレイヤー", 
            "移動", 
            {"target_spot_id": "test_spot"}
        )
        
        assert result.success == False
        assert "プレイヤー 存在しないプレイヤー が見つかりません" in result.message

    def test_get_action_help_for_llm(self):
        """LLM用ヘルプ情報取得テスト"""
        help_info = self.orchestrator.get_action_help_for_llm("test_player")
        
        assert 'available_actions_count' in help_info
        assert 'action_types' in help_info
        assert 'usage_instructions' in help_info
        
        # 状態ベースに変更されたため state_specific を確認
        assert help_info['action_types']['state_specific'] > 0
        assert 'action_selection' in help_info['usage_instructions']
        assert 'argument_format' in help_info['usage_instructions']

    def test_get_action_candidates_for_llm_no_player(self):
        """プレイヤーが存在しない場合のテスト"""
        candidates = self.orchestrator.get_action_candidates_for_llm("存在しないプレイヤー")
        assert candidates == []

    def test_get_action_candidates_for_llm_no_spot(self):
        """スポットが存在しない場合のテスト"""
        self.player.set_current_spot_id("存在しないスポット")
        candidates = self.orchestrator.get_action_candidates_for_llm("test_player")
        assert candidates == []

    def test_execute_llm_action_with_chest(self):
        """宝箱アクション実行テスト"""
        # スポットに宝箱を追加
        chest = Chest("test_chest", "テスト宝箱")
        self.spot.add_interactable(chest)
        
        # 宝箱を開けるアクションを実行
        result = self.orchestrator.execute_llm_action(
            "test_player", 
            "宝箱を開ける", 
            {"chest_name": "テスト宝箱"}
        )
        
        assert result.success == True

    def test_execute_llm_action_with_bulletin_board(self):
        """掲示板アクション実行テスト"""
        # スポットに掲示板を追加
        board = BulletinBoard("test_board", "テスト掲示板")
        self.spot.add_interactable(board)
        
        # 掲示板に書き込むアクションを実行
        result = self.orchestrator.execute_llm_action(
            "test_player", 
            "掲示板に書き込む", 
            {"board_name": "掲示板", "content": "テスト投稿"}
        )
        
        assert result.success == True

    def test_execute_llm_action_with_monument(self):
        """石碑アクション実行テスト"""
        # スポットに石碑を追加
        monument = Monument("test_monument", "テスト石碑", "テスト用の石碑")
        self.spot.add_interactable(monument)
        
        # 石碑を読むアクションを実行
        result = self.orchestrator.execute_llm_action(
            "test_player", 
            "石碑を読む", 
            {"monument_name": "石碑"}
        )
        
        assert result.success == True 