"""スポットグラフ固有イベント用の観測 formatter (ディスパッチャ)。

方針: 自分の行動結果はツール結果で返すため、行為者本人には観測を生成しない。
他プレイヤーには social カテゴリで配信し、環境変化は environment で全員に配信する。

カテゴリ別に handler を分離 (元 formatter が 1100 行を超えたため):
- `_spot_graph_movement_handler`        : 入退場/探索/prepared action
- `_spot_graph_object_handler`          : object/connection/state/public effect
- `_spot_graph_monster_handler`         : モンスター出現/退場/攻撃/捕食/採食
- `_spot_graph_monster_reaction_handler`: FLEE/CHASE/温度/Pack 連動 (Phase 4a/4-O)
- `_spot_graph_sound_handler`           : 環境音 (Phase 5)

本ファイルは各 handler を順に試して最初に非 None を返したものを返すだけの薄い
ディスパッチャ。event 種別の追加は対応 handler の `format()` 分岐に追加する。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters._spot_graph_monster_handler import (
    SpotGraphMonsterHandler,
)
from ai_rpg_world.application.observation.services.formatters._spot_graph_monster_reaction_handler import (
    SpotGraphMonsterReactionHandler,
)
from ai_rpg_world.application.observation.services.formatters._spot_graph_movement_handler import (
    SpotGraphMovementHandler,
)
from ai_rpg_world.application.observation.services.formatters._spot_graph_object_handler import (
    SpotGraphObjectHandler,
)
from ai_rpg_world.application.observation.services.formatters._spot_graph_sound_handler import (
    SpotGraphSoundHandler,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class SpotGraphObservationFormatter:
    """SpotGraph ドメインイベントを他プレイヤー向け観測に変換する。

    行為者本人は常に None (ツール結果で十分)。
    ConnectionStateChangedEvent / SpotObjectStateChangedEvent は行為者不明の
    環境変化として全受信者に配信する。

    実装は handler を 5 つに分割し、本クラスは順番に `format()` を呼ぶだけ。
    """

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._handlers = (
            SpotGraphMovementHandler(context),
            SpotGraphObjectHandler(context),
            SpotGraphMonsterHandler(context),
            SpotGraphMonsterReactionHandler(context),
            SpotGraphSoundHandler(context),
        )

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        for handler in self._handlers:
            result = handler.format(event, recipient_player_id)
            if result is not None:
                return result
        return None
