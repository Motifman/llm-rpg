from dataclasses import dataclass, field
from typing import List
from src.domain.conversation.message import Message


@dataclass
class MessageBox:
    messages: List[Message] = field(default_factory=list)

    def append(self, message: Message):
        self.messages.append(message)
    
    def read_all(self) -> List[Message]:
        all_messages = self.messages[:]
        self.messages.clear()
        return all_messages