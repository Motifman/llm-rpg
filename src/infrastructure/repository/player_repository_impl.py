from typing import List, Optional, Dict, Any
from src.domain.player.repository.player_repository import PlayerRepository
from src.infrastructure.mocks.mock_player import MockPlayer, create_mock_players


class PlayerRepositoryImpl(PlayerRepository):
    """PlayerRepositoryの実装クラス（モック版）"""

    def __init__(self):
        # 実際の実装ではデータベース接続など
        # ここではメモリ上にデータを保持する簡易実装
        self._players: Dict[int, MockPlayer] = {}
        self._next_id = 1
        
        # サンプルプレイヤーデータを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルプレイヤーデータのセットアップ"""
        mock_players = create_mock_players()
        for player in mock_players:
            self._players[player.player_id] = player

    def find_by_id(self, player_id: int) -> Optional[MockPlayer]:
        """プレイヤーIDでプレイヤーを検索"""
        return self._players.get(player_id)

    def find_by_name(self, name: str) -> Optional[MockPlayer]:
        """名前でプレイヤーを検索"""
        for player in self._players.values():
            if player.name == name:
                return player
        return None

    def find_by_spot_id(self, spot_id: int) -> List[MockPlayer]:
        """指定されたスポットにいるプレイヤーを検索"""
        return [player for player in self._players.values()
                if player.current_spot_id == spot_id]

    def find_by_battle_id(self, battle_id: int) -> List[MockPlayer]:
        """指定された戦闘に参加しているプレイヤーを検索"""
        # TODO: 実際の実装ではbattle_playerテーブルなどから取得
        # ここでは簡易実装として、戦闘状態を持つプレイヤーを返す
        return [player for player in self._players.values()
                if hasattr(player, '_battle_id') and getattr(player, '_battle_id', None) == battle_id]

    def find_by_role(self, role) -> List[MockPlayer]:
        """指定されたロールのプレイヤーを検索"""
        return [player for player in self._players.values() if player.role == role]

    def save(self, player: MockPlayer) -> None:
        """プレイヤーを保存"""
        self._players[player.player_id] = player

    def delete(self, player_id: int) -> None:
        """プレイヤーを削除"""
        if player_id in self._players:
            del self._players[player_id]

    def find_all(self) -> List[MockPlayer]:
        """全てのプレイヤーを取得"""
        return list(self._players.values())

    def exists_by_id(self, player_id: int) -> bool:
        """プレイヤーIDが存在するかチェック"""
        return player_id in self._players

    def exists_by_name(self, name: str) -> bool:
        """名前が存在するかチェック"""
        return any(player.name == name for player in self._players.values())

    def count(self) -> int:
        """プレイヤーの総数を取得"""
        return len(self._players)

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのプレイヤーを削除（テスト用）"""
        self._players.clear()
        self._next_id = 1

    def generate_player_id(self) -> int:
        """新しいプレイヤーIDを生成（テスト用）"""
        player_id = self._next_id
        self._next_id += 1
        return player_id

    def find_by_ids(self, player_ids: List[int]) -> List[MockPlayer]:
        """複数のプレイヤーIDでプレイヤーを検索"""
        result = []
        for player_id in player_ids:
            player = self._players.get(player_id)
            if player:
                result.append(player)
        return result
