"""``interact`` tool 用の共通 helper。

PR-θ3 (経路統合): 旧 runtime_manager 内 module-level 関数
``_interact_remediation_for_reason`` / ``_list_object_interactions`` を
application 層に移した。SpotGraphToolExecutor._interact が新経路として
これらを使う。runtime_manager 側は移行完了までは本 module を経由して同じ
実装を参照する (旧 handler は削除済み)。

## Why here (application 層)

- SpotGraphToolExecutor は application 層。runtime_manager は presentation 層。
- interact の失敗 remediation / 利用可能操作列挙は「LLM に返す文面を組み立てる
  business logic」なので application 層に置くのが正しい向き。
"""

from __future__ import annotations

import logging
from typing import Any, List

from ai_rpg_world.application.world_graph.hidden_interaction_filter import (
    hidden_failure_messages_from_state,
    visible_action_names,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

logger = logging.getLogger(__name__)


def list_object_interactions(
    runtime: Any, world_object_id: int, *, player_id: int
) -> List[str]:
    """``world_object_id`` が所属する spot の interior から available action 名を列挙。

    実験 #26 で LLM が "search" / "examine" 等の ad-hoc action_name を発明して
    InteractionNotFoundException が generic error に化けていた問題を直すため、
    handler が remediation で正規の action 一覧を返せるようにするヘルパ。
    解決経路で例外が出たら空 list を返す (= remediation 文面が "(なし)" になる)。

    PR-B (Y_after_issue621 後続): 旧版は ``id_mapper.get_str(...)`` で変換した
    str を受け取って ``interior.get_object(SpotObjectId)`` に渡していたため、
    型不一致で常に None → 空 list を返していた。LLM は「利用可能な操作: (なし)」
    を毎回受け取り、定義されている action_name を学習できなかった。
    引数を ``world_object_id: int`` に統一し、内部で SpotObjectId に包む。

    **``player_id`` は必須。** 渡し忘れは ``TypeError`` で即死する。空を
    返す形も考えたが、**空になるのもそれはそれで静かな失敗**で、案内が
    丸ごと死んだことに誰も気づけない (claude の指摘)。旧版は全操作を
    そのまま並べており、**役割で伏せた操作まで名前ごと教えていた**。

        利用可能な操作: log_weather, log_weather_2, log_weather_3, log_weather_pretend

    実 run 011 でクルーがこの一覧から ``count_supplies_pretend`` を読み取り、
    2 手番後に呼んでいる。さらに別のオブジェクトへ ``check_generator_pretend``
    を試しており、**偽装版という仕組みそのものを学習していた**。候補一覧の
    側では行ごと消しているのに、こちらで教えていた。

    判断は ``hidden_interaction_filter`` に 1 つだけ置く。
    """
    try:
        # SpotObjectId.create は int / str どちらでも受け付け、不正値は例外を
        # 投げる。本関数は best-effort で「分からないなら空 list」を返すため、
        # 例外は外側 except で握る。
        target_object_id = SpotObjectId.create(world_object_id)
        graph = runtime._spot_graph_repo.find_graph()
        # SpotObjectId から所属 spot を探す。spot interior repository に
        # 直接の逆引きが無いので spot を全列挙する (= O(N) だが失敗時のみ
        # 走るので許容)。
        for node in graph.iter_spot_nodes():
            interior = runtime._spot_interior_repo.find_by_spot_id(node.spot_id)
            if interior is None:
                continue
            obj = interior.get_object(target_object_id)
            if obj is not None:
                player = runtime._player_status_repo.find_by_id(
                    PlayerId(player_id)
                )
                return visible_action_names(obj.interactions, player)
        return []
    except Exception:
        # 「絞った結果 0 件」と「壊れて 0 件」を外から区別できないので、
        # せめて記録は残す。案内が黙って死ぬのを見えるようにする。
        logger.warning(
            "list_object_interactions failed for world_object_id=%s player_id=%s",
            world_object_id,
            player_id,
            exc_info=True,
        )
        return []


def hidden_object_interaction_failure_reason(
    runtime: Any, world_object_id: int, *, player_id: int
) -> str:
    """本人に伏せた操作しか無い物体について、宣言済みの理由だけを返す。

    操作名は一切返さない。異なる理由が複数ある場合は、どの秘密の操作へ対応
    するか推測できない一般文へ倒す。通常の ``station_drill`` では同じ
    ``failure_message`` に統一されているため、作者が書いた理由がそのまま届く。

    行為者の現在地だけを見る。物体 ID は世界内で一意でも、この関数は目の前の
    対象を解決した後の拒否理由を返す入口であり、別の部屋の情報を答えない。

    repository や graph の例外は握りつぶさない。空文字へ縮退すると、呼び出し側が
    既知の誤誘導である「利用可能な操作: (なし)」を返し、配線障害と「理由なし」を
    区別できなくなるためである。
    """
    target_object_id = SpotObjectId.create(world_object_id)
    graph = runtime._spot_graph_repo.find_graph()
    spot_id = graph.get_entity_spot(EntityId.create(player_id))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    if interior is None:
        return ""
    obj = interior.get_object(target_object_id)
    if obj is None:
        return ""
    player = runtime._player_status_repo.find_by_id(PlayerId(player_id))
    if visible_action_names(obj.interactions, player):
        return ""
    actor_state = dict(getattr(player, "state", {}) or {}) if player else {}
    reasons: list[str] = []
    for interaction in obj.interactions:
        for reason in hidden_failure_messages_from_state(interaction, actor_state):
            if reason not in reasons:
                reasons.append(reason)
    if len(reasons) == 1:
        return reasons[0]
    if reasons:
        return "その物体の手順は現在の自分には使えない。"
    return ""


__all__ = [
    "hidden_object_interaction_failure_reason",
    "list_object_interactions",
]
