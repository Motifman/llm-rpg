from typing import List, Dict, Optional
from game.player.player import Player


class PlayerManager:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.spot_to_player_ids: Dict[str, List[str]] = {}

    def add_player(self, player: Player):
        self.players[player.get_player_id()] = player

    def get_player(self, player_id: str) -> Player:
        return self.players.get(player_id)
    
    def get_all_players(self) -> List[Player]:
        return list(self.players.values())

    # === スポット別インデックス機能 ===
    def rebuild_spot_index(self) -> None:
        """現在登録されている全プレイヤーから、スポットIDごとのプレイヤーID一覧インデックスを再構築して保存する。

        計算コストを抑えるため、ゲームループの適切なタイミング（ターン境界など）で呼び出すことを想定。
        """
        new_index: Dict[str, List[str]] = {}
        for player in self.players.values():
            spot_id = player.get_current_spot_id()
            if not spot_id:
                continue
            if spot_id not in new_index:
                new_index[spot_id] = []
            new_index[spot_id].append(player.get_player_id())
        self.spot_to_player_ids = new_index

    def get_player_ids_at_spot(self, spot_id: str, exclude_player_id: Optional[str] = None) -> List[str]:
        """インデックスから指定スポットにいるプレイヤーID一覧を取得する。
        exclude_player_id が指定された場合、そのIDは結果から除外する。
        インデックス未構築時や該当無しの場合は空配列を返す。
        """
        ids = self.spot_to_player_ids.get(spot_id, [])
        if exclude_player_id is None:
            return list(ids)
        return [pid for pid in ids if pid != exclude_player_id]

    def get_coplayer_ids_in_same_spot(self, player_id: str, include_self: bool = False) -> List[str]:
        """与えられたプレイヤーと同じスポットにいるプレイヤーID一覧を返す。
        include_self=False の場合は本人を除外する。プレイヤー不在や現在地不明なら空配列。
        """
        player = self.get_player(player_id)
        if not player:
            return []
        spot_id = player.get_current_spot_id()
        if not spot_id:
            return []
        if include_self:
            return self.get_player_ids_at_spot(spot_id)
        return self.get_player_ids_at_spot(spot_id, exclude_player_id=player_id)