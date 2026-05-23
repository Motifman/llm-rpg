"""Sub-formatter 共通の名前解決・リポジトリ参照。親への依存を避けるための基盤。"""

from dataclasses import dataclass
from typing import Any, List, Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
        ISpotGraphRepository,
    )
    from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
        SoundPropagationService,
    )


def _coerce_item_spec_id_entry_value(raw: Any) -> Optional[int]:
    """
    obtained_items 内 dict の item_spec_id を int に正規化する。
    `episodic_cue_rules._coerce_non_bool_int` と同じ規則（bool は int とみなさない）。
    """
    if type(raw) is int:
        return raw
    if isinstance(raw, float):
        if raw.is_integer():
            return int(raw)
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s or not s.isdigit():
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def resolve_item_spec_id_value_for_instance(
    item_repository: Optional["ItemRepository"],
    item_instance_id: ItemInstanceId,
) -> Optional[int]:
    """ItemAggregate が取れるとき item_spec_id の数値を返す。"""
    if item_repository is None:
        return None
    agg = item_repository.find_by_id(item_instance_id)
    if agg is None:
        return None
    return agg.item_spec.item_spec_id.value


def first_item_spec_id_value_from_obtained_items(
    obtained_items: List[Any],
) -> Optional[int]:
    """
    ResourceHarvestedEvent.obtained_items などから先頭の item_spec_id を int で返す。
    複数種ある場合は先頭のみ（局面 cue は 1 件に収めるため）。
    各要素の item_spec_id は `_coerce_item_spec_id_entry_value` で解釈する。
    """
    for entry in obtained_items:
        if not isinstance(entry, dict):
            continue
        spec_id_raw = entry.get("item_spec_id")
        if spec_id_raw is None:
            continue
        coerced = _coerce_item_spec_id_entry_value(spec_id_raw)
        if coerced is not None:
            return coerced
    return None


@dataclass(frozen=True)
class ObservationFormatterContext:
    """
    Sub-formatter が親に依存せず名前解決・アイテム参照を行うための読み取り専用コンテキスト。
    Phase 2 以降で各 formatter がロジックを持つ際に使用する。
    """

    name_resolver: ObservationNameResolver
    item_repository: Optional["ItemRepository"]
    spot_graph_repository: Optional["ISpotGraphRepository"] = None
    sound_propagation_service: Optional["SoundPropagationService"] = None

    def lookup_recipient_spot(
        self, recipient_player_id: PlayerId
    ) -> Optional[SpotId]:
        """observer (player) の現在 spot を引く。

        Issue #184 (軸 3) の位置ベース prose 分岐用。spot_graph_repository が
        未注入 / entity がグラフ上に置かれていない場合は ``None`` を返し、
        formatter 側で位置非依存の fallback prose に倒せるようにする。
        """
        if self.spot_graph_repository is None:
            return None
        try:
            graph = self.spot_graph_repository.find_graph()
            return graph.get_entity_spot(EntityId.create(int(recipient_player_id)))
        except Exception:
            # 例外の種類はリポジトリ実装依存。観測 prose に失敗を漏らさず
            # 「位置不明」として None を返すのが正しい振る舞い。
            return None
