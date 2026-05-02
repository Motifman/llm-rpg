"""会話チャネルとスポットグラフ上の音量の対応"""

from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.world_graph.enum.sound_volume import SoundVolumeEnum


def speech_channel_to_sound_volume(channel: SpeechChannel) -> SoundVolumeEnum:
    if channel == SpeechChannel.WHISPER:
        return SoundVolumeEnum.WHISPER
    if channel == SpeechChannel.SAY:
        return SoundVolumeEnum.NORMAL
    return SoundVolumeEnum.SHOUT
