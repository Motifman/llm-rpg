"""プレイヤー間発言のコマンド"""

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


@dataclass(frozen=True)
class SpeakCommand:
    """発言コマンド（囁き・発言・シャウト）"""

    speaker_player_id: int
    content: str
    channel: SpeechChannel
    target_player_id: Optional[int] = None  # WHISPER 時のみ使用
