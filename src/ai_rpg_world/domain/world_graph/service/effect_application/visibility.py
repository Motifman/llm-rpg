from __future__ import annotations

import logging
from typing import FrozenSet, List, Optional, Tuple

from ai_rpg_world.domain.world_graph.enum.effect_visibility import EffectVisibility
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    StateDeltaEntry,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)

_logger = logging.getLogger(__name__)


# 効果ごとの既定の可視性。シナリオ JSON で `visibility` を明示すれば上書きされる。
# - 行為者本人の体験 (痛み、回復、自分の持ち物変化) → ACTOR_DIRECT
# - 環境・接続・対象オブジェクトの物理変化 → PUBLIC_OBSERVABLE
# - 内部 bookkeeping (tick 記録、フラグ) → HIDDEN
DEFAULT_VISIBILITY: dict[InteractionEffectTypeEnum, EffectVisibility] = {
    InteractionEffectTypeEnum.CHANGE_OBJECT_STATE: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE: EffectVisibility.HIDDEN,
    # 投入の進捗は object.state / state_display を真実源にする。別途
    # witness_observation_message が行為を伝えるため、効果サマリは重複させない。
    InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT: EffectVisibility.HIDDEN,
    # gold の投入も同じ理由で進捗は真実源に譲るが、支払った本人には
    # 「いくら減ったか」が要るので actor には出す。
    InteractionEffectTypeEnum.DEPOSIT_GOLD_TO_OBJECT: EffectVisibility.ACTOR_DIRECT,
    # 備蓄消費は内部 bookkeeping。観測は対の GIVE_ITEM / SHOW_MESSAGE 側で出る。
    InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK: EffectVisibility.HIDDEN,
    InteractionEffectTypeEnum.GIVE_FROM_LOOT_TABLE: EffectVisibility.ACTOR_DIRECT,
    InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK: EffectVisibility.HIDDEN,
    InteractionEffectTypeEnum.REVEAL_OBJECT: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.REVEAL_SUB_LOCATION: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE: EffectVisibility.ACTOR_DIRECT,
    InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK: EffectVisibility.HIDDEN,
    InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: EffectVisibility.HIDDEN,
    InteractionEffectTypeEnum.CHANGE_PLAYER_STATE: EffectVisibility.HIDDEN,
    InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK: EffectVisibility.HIDDEN,
    # 痛みは内臓的だが、流血・よろめき・倒れるなどは同スポットの他者から見える。
    # 「自分が痛い」は messages のテキストで本人に伝わるため、構造化サマリは
    # 第三者観測側にデフォルトを倒す。本人は自分の HP / state 変化を
    # 現在状態セクションから読む。
    InteractionEffectTypeEnum.APPLY_DAMAGE: EffectVisibility.PUBLIC_OBSERVABLE,
    # POISON のように内臓的なものから PARALYSIS のように見えるものまで幅がある。
    # 既定は安全側 (ACTOR_DIRECT) に置き、シナリオ側で見える状態異常 (PARALYSIS,
    # SLEEP 等) は visibility を PUBLIC_OBSERVABLE に明示する運用とする。
    InteractionEffectTypeEnum.APPLY_STATUS_EFFECT: EffectVisibility.ACTOR_DIRECT,
    # 転移は同スポットの他者から「いきなり消えた」と見える物理現象。
    InteractionEffectTypeEnum.TELEPORT_ENTITY: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.CHANGE_ATMOSPHERE: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.CREATE_CONNECTION: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.DESTROY_CONNECTION: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.SATISFY_NEED: EffectVisibility.ACTOR_DIRECT,
    # ボタンを押す行為はその場の全員に見える。誰が押したかは会議の
    # 出発点になる情報なので隠さない。
    InteractionEffectTypeEnum.CALL_MEETING: EffectVisibility.PUBLIC_OBSERVABLE,
    InteractionEffectTypeEnum.SET_FLAG: EffectVisibility.HIDDEN,
    InteractionEffectTypeEnum.CLEAR_FLAG: EffectVisibility.HIDDEN,
    # 参照先の flag 効果へ展開され、自身は観測を作らない。
    InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION: EffectVisibility.HIDDEN,
    InteractionEffectTypeEnum.SHOW_MESSAGE: EffectVisibility.ACTOR_DIRECT,
    InteractionEffectTypeEnum.SHOW_ROOM_OCCUPANCY: EffectVisibility.ACTOR_DIRECT,
    InteractionEffectTypeEnum.GIVE_ITEM: EffectVisibility.ACTOR_DIRECT,
    InteractionEffectTypeEnum.REMOVE_ITEM: EffectVisibility.ACTOR_DIRECT,
    InteractionEffectTypeEnum.COMBINE_ITEMS: EffectVisibility.ACTOR_DIRECT,
    # PR-F: 看板に書き込む行為は物理的な変化であり、同スポットの他者から
    # 「誰かが書き込んでいる」と見える (CHANGE_OBJECT_STATE と同じ既定)。
    InteractionEffectTypeEnum.WRITE_PLAYER_TEXT: EffectVisibility.PUBLIC_OBSERVABLE,
    # 看板を読む行為そのものは他者に観測されない (SHOW_MESSAGE と同じ扱い)。
    # 読んだ内容を他者に広めるかどうかは、読んだ本人が speech で発話するかに
    # 委ねる (= 伝聞抽出の入口は speech 側であり、この effect ではない)。
    InteractionEffectTypeEnum.SHOW_PLAYER_TEXT: EffectVisibility.ACTOR_DIRECT,
}


def validate_default_visibility_coverage() -> None:
    """モジュール読込時に、全効果へ既定可視性が宣言済みか検査する。"""
    missing = [
        effect_type
        for effect_type in InteractionEffectTypeEnum
        if effect_type not in DEFAULT_VISIBILITY
    ]
    if missing:
        raise AssertionError(
            f"DEFAULT_VISIBILITY に未登録の InteractionEffectTypeEnum: {missing}"
        )


validate_default_visibility_coverage()


def resolve_visibility(effect: InteractionEffect) -> EffectVisibility:
    """effect の visibility を effect.visibility (first-class field) →
    parameters['visibility'] (legacy 経路、警告ログ付き) → 既定値の順で解決する。

    parameters 側の経路は scenario_loader 経由で過渡期に流入する可能性が
    あるための後方互換であり、新規呼び出しは effect.visibility を使うこと。
    """

    if effect.visibility is not None:
        return effect.visibility

    raw = effect.parameters.get("visibility")
    if raw is not None:
        _logger.warning(
            "InteractionEffect.parameters['visibility'] is deprecated for %s; "
            "use the first-class `visibility` field instead",
            effect.effect_type.value,
        )
        if isinstance(raw, EffectVisibility):
            return raw
        if isinstance(raw, str) and raw:
            try:
                return EffectVisibility(raw)
            except ValueError:
                _logger.warning(
                    "Unknown effect visibility %r for %s; falling back to default",
                    raw,
                    effect.effect_type.value,
                )
    return DEFAULT_VISIBILITY[effect.effect_type]


_MISSING = object()


def state_delta_entries(
    before: Optional[dict],
    after: dict,
    *,
    exclude_keys: FrozenSet[str] = frozenset(),
) -> Tuple[StateDeltaEntry, ...]:
    """state map の before/after から変更箇所だけを抜き出す。

    `before` に存在しなかったキーと、`before` に明示的に `None` が入って
    いたキーを区別する必要がある（後者を `before=None, after=...` として
    残すため）。同様に `after` で消えたキーも、値が None なのか削除なのか
    の判別が必要。`dict.get` の戻り値だけでは区別不能なので sentinel を使う。
    `before==after` の場合はエントリを生成しない。

    `exclude_keys` は「行為が起きたことは見せてよいが、値そのものは第三者
    観測イベント (state_delta) に乗せたくない」key を落とすためのもの
    (PR-J: 看板の本文 / 書き手名 / tick)。`hidden_state_keys` (プロンプトの
    現在状態表示から除外) とは独立した経路なので、こちらでも明示的に除外
    する必要がある。
    """

    if before is None:
        before = {}
    keys = (set(before.keys()) | set(after.keys())) - set(exclude_keys)
    entries: List[StateDeltaEntry] = []
    for key in sorted(keys, key=str):
        b = before.get(key, _MISSING)
        a = after.get(key, _MISSING)
        if b == a:
            continue
        entries.append(
            StateDeltaEntry(
                key=str(key),
                before=None if b is _MISSING else b,
                after=None if a is _MISSING else a,
            )
        )
    return tuple(entries)
