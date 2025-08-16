from src.domain.player.player import Player
from src.domain.conversation.message import Message
from typing import List
from datetime import datetime


class ConversationService:
    def __init__(self):
        pass
    
    def send_message_to_spot(self, sender: Player, recipients: List[Player], content: str, timestamp: datetime):
        for recipient in recipients:
            if sender.player_id == recipient.player_id:
                raise ValueError("Sender and recipient cannot be the same player")
            if sender.current_spot_id != recipient.current_spot_id:
                raise ValueError("Sender and recipient must be in the same spot")
            message = Message.create(sender.player_id, sender.name, recipient.player_id, content, timestamp)
            recipient.receive_message(message)
    
    def send_message_to_player(self, sender: Player, recipient: Player, content: str, timestamp: datetime):
        if sender.player_id == recipient.player_id:
            raise ValueError("Sender and recipient cannot be the same player")
        if sender.current_spot_id != recipient.current_spot_id:
            raise ValueError("Sender and recipient must be in the same spot")
        message = Message.create(sender.player_id, sender.name, recipient.player_id, content, timestamp)
        recipient.receive_message(message)