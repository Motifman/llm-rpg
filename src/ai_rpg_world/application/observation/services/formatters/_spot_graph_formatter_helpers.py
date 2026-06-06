"""SpotGraph formatter 群の共通ヘルパー。

複数の handler ファイルで再利用する小道具:
- `_SpotGraphFormatterBase`: name 解決と self 判定を提供する基底
- `_derive_delta` / `_format_delta_text`: state delta テキスト化
- `_INCAPACITATION_SUFFIX_*`: 戦闘 prose 用の文末 suffix
- `_INTENSITY_PROSE`: Phase 5 環境音の強度 → 日本語マッピング

handler ファイル分割 (HIGH-3 リファクタ) で `spot_graph_formatter.py` が
1100 行を超えた状況を解消する際に切り出した。意味的には元 formatter の
private 実装と等価。
"""

from typing import Any

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    StateDeltaEntry,
)


# 攻撃で対象が「行動不能」になった際の suffix。被害者ごとに自然な日本語を
# 維持するため、player target / monster target を分けて持つ (field 自体は
# `target_incapacitated` で対称化済み)。
_INCAPACITATION_SUFFIX_FOR_PLAYER_TARGET = " 致命的なダメージで倒れた。"
_INCAPACITATION_SUFFIX_FOR_MONSTER_TARGET = " 致命傷を与えて倒した。"


# Phase 5: SpotSoundHeardEvent.intensity (str) を prose 用文言にマッピング。
# SoundIntensityEnum.value と同じ文字列をキーに使う。
# SILENT はそもそも event 発火しないので prose 不要。
_INTENSITY_PROSE: dict[str, str] = {
    "FAINT": "かすかな音",
    "MODERATE": "音",
    "LOUD": "大きな音",
}


class _SpotGraphFormatterBase:
    """各 handler が共有する name 解決ヘルパーの基底。

    `ObservationFormatterContext` を保持し、entity / spot / object の
    日本語名解決を集中させる。handler 側ではこれらのメソッドを使うだけで
    repository の例外処理を意識しなくて済む。
    """

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def _is_self(self, entity_id: Any, recipient_id: PlayerId) -> bool:
        return entity_id.value == recipient_id.value

    def _resolve_entity_name(self, entity_id: Any) -> str:
        return self._context.name_resolver.player_name(PlayerId(entity_id.value))

    def _resolve_spot_name(self, spot_id: Any) -> str:
        repo = self._context.spot_graph_repository
        if repo is None:
            return "不明なスポット"
        try:
            graph = repo.find_graph()
            return graph.get_spot(spot_id).name
        except Exception:
            return "不明なスポット"

    def _resolve_object_name(self, spot_id: Any, object_id: Any) -> str:
        # 実験 #26 で発覚: scenario loader は SpotNode.interior=None で構築し、
        # 実体は別 repo (SpotInteriorRepository) に住んでいる。graph 経由だけ
        # では object name が引けず "何か" fallback に落ちて prose に漏れて
        # いた (#373 失敗観測で 92/92 が "リオが何かのsearchを試みた" 状態)。
        # 1. graph.get_spot(spot_id).interior が有るならそれを優先 (旧経路、
        #    将来 interior が graph に再統合される可能性に備える)
        # 2. 無ければ spot_interior_repository.find_by_spot_id でリアル interior を引く
        # 3. それでも見つからなければ fallback "何か"
        try:
            repo = self._context.spot_graph_repository
            if repo is not None:
                graph = repo.find_graph()
                spot = graph.get_spot(spot_id)
                if spot.interior is not None:
                    obj = spot.interior.get_object(object_id)
                    if obj is not None:
                        return obj.name
            interior_repo = getattr(
                self._context, "spot_interior_repository", None
            )
            if interior_repo is not None:
                interior = interior_repo.find_by_spot_id(spot_id)
                if interior is not None:
                    obj = interior.get_object(object_id)
                    if obj is not None:
                        return obj.name
        except Exception:
            pass
        return "何か"


def _derive_delta(old_state: dict, new_state: dict):
    """formatter 側のフォールバック: event に state_delta が無いとき
    old_state / new_state を比較して StateDeltaEntry tuple を作る。
    """
    keys = set(old_state.keys()) | set(new_state.keys())
    out = []
    _SENTINEL = object()
    for key in sorted(keys, key=str):
        b = old_state.get(key, _SENTINEL)
        a = new_state.get(key, _SENTINEL)
        if b == a:
            continue
        out.append(
            StateDeltaEntry(
                key=str(key),
                before=None if b is _SENTINEL else b,
                after=None if a is _SENTINEL else a,
            )
        )
    return tuple(out)


def _format_delta_text(delta) -> str:
    """StateDeltaEntry tuple を観測テキスト用の短い日本語に変換する。"""
    if not delta:
        return ""
    fragments = []
    for d in delta:
        if d.before is None and d.after is not None:
            fragments.append(f"{d.key}が{d.after}になった")
        elif d.after is None and d.before is not None:
            fragments.append(f"{d.key}が消えた")
        else:
            fragments.append(f"{d.key}が{d.before}から{d.after}に変わった")
    return "、".join(fragments)
