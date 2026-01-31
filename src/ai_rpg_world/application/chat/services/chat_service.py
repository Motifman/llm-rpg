from typing import Optional
from ai_rpg_world.domain.common.notifier import Notifier
from ai_rpg_world.domain.player.player_repository import PlayerRepository
from ai_rpg_world.domain.spot.spot_repository import SpotRepository


class ChatApplicationService:
    def __init__(self, player_repository: PlayerRepository, spot_repository: SpotRepository, notifier: Notifier):
        self._player_repository = player_repository
        self._spot_repository = spot_repository
        self._notifier = notifier
    
    def send_message(self, sender_id: int, message: str, recipient_id: Optional[int] = None):
        if recipient_id:
            self._notifier.send_notification(recipient_id, message)
            return
        
        sender = self._player_repository.find_by_id(sender_id)
        if not sender:
            return
        
        recipient_ids = self._spot_repository.find_by_id(sender.spot_id).get_current_player_ids() - {sender_id}
        self._notifier.send_notification_to_all(recipient_ids, message)