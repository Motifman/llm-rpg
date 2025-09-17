from src.domain.common.event_handler import EventHandler
from src.domain.spot.spot_events import PlayerEnteredSpotEvent, PlayerExitedSpotEvent
from src.domain.player.player_repository import PlayerRepository
from src.domain.spot.spot_repository import SpotRepository
from src.domain.common.notifier import Notifier


class PlayerEnteredSpotNotificationHandler(EventHandler[PlayerEnteredSpotEvent]):
    """プレイヤーがスポットに入った時の通知を送信するハンドラー"""
    def __init__(self, player_repository: PlayerRepository, spot_repository: SpotRepository, notifier: Notifier):
        self._player_repository = player_repository
        self._spot_repository = spot_repository
        self._notifier = notifier
    
    def handle(self, event: PlayerEnteredSpotEvent):
        moved_player = self._player_repository.find_by_id(event.player_id)
        if not moved_player:
            return 
        
        destination_spot = self._spot_repository.find_by_id(event.spot_id)
        if not destination_spot:
            return
        
        spot_info = destination_spot.get_spot_summary()
        
        other_player_ids = destination_spot.get_current_player_ids() - {event.player_id}
        if not other_player_ids:
            return
        
        other_player_info = []
        for other_player_id in other_player_ids:
            other_player = self._player_repository.find_by_id(other_player_id)
            if not other_player:
                continue
            other_player_info.append(other_player.get_player_summary())
        
        players_text = ", ".join(other_player_info) if other_player_info else "誰もいません"
        message_content = f"[移動完了] {spot_info}\n現在このスポットにいるプレイヤー: {players_text}"
        
        self._notifier.send_notification(moved_player.player_id, message_content)


class JoinOtherPlayerNotificationHandler(EventHandler[PlayerEnteredSpotEvent]):
    """他のプレイヤーがスポットに入った時の通知を送信するハンドラー"""
    def __init__(self, player_repository: PlayerRepository, spot_repository: SpotRepository, notifier: Notifier):
        self._player_repository = player_repository
        self._spot_repository = spot_repository
        self._notifier = notifier
    
    def handle(self, event: PlayerEnteredSpotEvent):
        moved_player = self._player_repository.find_by_id(event.player_id)
        if not moved_player:
            return

        destination_spot = self._spot_repository.find_by_id(event.spot_id)
        if not destination_spot:
            return
        
        other_player_ids = destination_spot.get_current_player_ids() - {event.player_id}
        if not other_player_ids:
            return

        for player_id in other_player_ids:
            existing_player = self._player_repository.find_by_id(player_id)
            if existing_player:
                message_content = f"[プレイヤー入室] {moved_player.name}が{destination_spot.name}(ID: {destination_spot.spot_id})に入りました"
                self._notifier.send_notification(existing_player.player_id, message_content)


class ExitOtherPlayerNotificationHandler(EventHandler[PlayerExitedSpotEvent]):
    """他のプレイヤーがスポットから出た時の通知を送信するハンドラー"""
    def __init__(self, player_repository: PlayerRepository, spot_repository: SpotRepository, notifier: Notifier):
        self._player_repository = player_repository
        self._spot_repository = spot_repository
        self._notifier = notifier
    
    def handle(self, event: PlayerExitedSpotEvent):
        moved_player = self._player_repository.find_by_id(event.player_id)
        if not moved_player:
            return
        
        destination_spot = self._spot_repository.find_by_id(event.spot_id)
        if not destination_spot:
            return
        
        other_player_ids = destination_spot.get_current_player_ids() - {event.player_id}
        if not other_player_ids:
            return

        for player_id in other_player_ids:
            existing_player = self._player_repository.find_by_id(player_id)
            if existing_player:
                message_content = f"[プレイヤー退去] {moved_player.name}が{destination_spot.name}(ID: {destination_spot.spot_id})から出ました"
                self._notifier.send_notification(existing_player.player_id, message_content)