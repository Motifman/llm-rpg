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

from typing import Any, List

from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


# N2: 「枯渇 / 同じ tick 内に再採取できない」系の失敗 reason を検知する
# キーワード集。マッチしたら「同じ object に同 action_name を retry しない」
# 旨の remediation に切り替える (= LLM が同じ枯渇 resource を回し続ける
# 無限 retry の抑制)。
_INTERACTION_EXHAUST_HINTS = (
    "採り尽く",
    "枯渇",
    "もう空",
    "もう開い",
    "すでに",
    "今は",
    "燃え上が",
)


def interact_remediation_for_reason(reason: str) -> str:
    """InteractionNotAllowedException の reason に応じた LLM 向け remediation。

    枯渇系キーワードが含まれるなら「同じ object を retry しない」旨、それ以外は
    「前提条件を満たしてから再試行」の汎用文言。
    """
    if any(k in reason for k in _INTERACTION_EXHAUST_HINTS):
        return (
            "同じ object に同 action_name を再試行しても結果は変わらない。"
            "別の場所・別 object・別 action を選ぶか、必要な前提アイテムを"
            "先に揃えてから戻ること。"
        )
    return (
        "前提条件 (必要アイテム / 体力 / 天候 / フラグ) を満たしてから再試行する。"
        "失敗 reason に名指しされたアイテムや状態を確認すること。"
    )


def list_object_interactions(runtime: Any, world_object_id: int) -> List[str]:
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
                return [i.action_name for i in obj.interactions]
        return []
    except Exception:
        return []


__all__ = [
    "interact_remediation_for_reason",
    "list_object_interactions",
]
