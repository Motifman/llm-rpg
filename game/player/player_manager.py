from typing import List
from game.player.player import Player


class PlayerManager:
    def __init__(self):
        self.players = {}

    def add_player(self, player: Player):
        self.players[player.get_player_id()] = player

    def get_player(self, player_id: str) -> Player:
        return self.players[player_id]
    
    def get_all_players(self) -> List[Player]:
        return list(self.players.values())