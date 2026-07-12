"""BeliefEvidence の cue_signature を決定論生成する。

U2 (証拠台帳統一設計 §2 U2): 「新しい抽出ロジックを発明しない」方針に従い、
``SubjectiveEpisode`` が既に持つ構造化フィールド (``action.tool_name`` /
``location.spot_id`` / ``who``) をそのまま使う。これらは
``ChunkEpisodeDraftBuilder`` が ``ChunkEncodingInput`` と
``build_situation_episodic_cues`` (``episodic_cue_rules.py``) 由来の cue
材料から既に構築済の値であり、本モジュールは新たな観測データを追加しない。

設計上のフォーマットは semantic_learning_consolidation_design.md の例
(``"tool:explore|spot:浜辺"``) に合わせ、``tool:<tool_name>`` を必ず先頭に
置き、続けて (あれば) ``spot:<spot_id>`` / ``player:<相手>`` を ``|`` 区切り
で並べる。同じ episode フィールドから常に同じ文字列が出る (= 決定論)。
"""

from __future__ import annotations

from typing import Any, Optional

from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

_TOOL_NAME_UNKNOWN = "none"

# P9 (伝聞): noun matcher の axis → cue_signature の軸名。伝聞の cue は
# 「その主張が何についてか」= 対象で決めるので、場所と人物だけを拾う。
_HEARSAY_AXIS_TO_CUE_PREFIX = {
    "place_spot": "spot",
    "entity": "player",
}

# noun matcher の entity 値形式 (world_noun_matcher._format_entity_value と一致)。
# 聞き手本人を指す entity マッチを self: 軸に振り分けるのに使う。
_SELF_ENTITY_VALUE_FMT = "spot_graph_player_{}"

# noun matcher の entity 値の接頭辞。id 部を取り出して直接体験 cue の
# 人物トークン形式へ揃えるのに使う (P10)。
_ENTITY_VALUE_PREFIX = "spot_graph_player_"
# 直接体験 cue が使う人物マーカー形式。belief evidence は
# belief_evidence_transcriber が chunk 完了点で作り、その cue は chunk episode
# の who から来る。chunk の who (chunk_episode_draft_builder._who_from_observations)
# は観測の actor だけを _actor_from_structured で "entity:actor:{id}" に整形した
# ものなので、伝聞の人物 cue もこの形式に揃えると、同一人物の伝聞と直接体験が
# cue_tokens で同じトークンになり、固着 shortlist で同じクラスタに寄る。
# (action_episode_draft_builder._collect_who は対象 player を "entity:player:{id}"
# で持つが、そちらは transcriber を経由せず belief evidence にならないので対象外。)
_DIRECT_ACTOR_VALUE_FMT = "entity:actor:{}"


def _to_direct_actor_value(entity_value: str) -> str:
    """noun matcher の entity 値 (``spot_graph_player_{id}``) を、直接体験 cue が
    使う who マーカー形式 (``entity:actor:{id}``) に揃える (P10)。

    id 部を取り出せない形 (接頭辞が付かない値) なら元の値のまま返す —
    揃えられないケースを silent に落とさず、少なくとも伝聞同士は寄る。
    """
    if entity_value.startswith(_ENTITY_VALUE_PREFIX):
        player_id = entity_value[len(_ENTITY_VALUE_PREFIX):]
        if player_id:
            return _DIRECT_ACTOR_VALUE_FMT.format(player_id)
    return entity_value


def build_hearsay_cue_signature(
    claim_text: str,
    noun_matcher: Optional[Any],
    *,
    self_player_id: Optional[int] = None,
) -> str:
    """伝聞の主張文から cue_signature を決める (P9)。

    claim の**対象** (何についての知識か) を noun matcher で拾い、場所なら
    ``spot:<id>``、人物なら ``player:<kind_id>`` にする。話者 (誰が言ったか) は
    ここに混ぜない — それは ``BeliefEvidence.source_speaker`` に分離して持つ
    (混ぜると「話者についての belief」に化ける。belief_hearsay_design.md §2)。

    対象が **自分自身** (聞き手本人) の場合は ``self:`` 軸にする — 「他者が自分に
    ついて語ったこと」を「その人物についての belief」と別クラスタに保つため
    (unified_full_001 のカイ「リオは自分の話を聞かない」型の自己認識)。
    ``self_player_id`` に聞き手の player_id を渡すと、その player を指す entity
    マッチを self として扱う。

    テキスト中で最初に現れた spot / player を対象とみなす。対象を特定できない
    (matcher 未配線 / 固有名詞なし) ときは空文字を返す — 固着パスが cue なし
    evidence として扱い、discard に委ねる (曖昧な対象を silent に捨てない)。
    """
    if noun_matcher is None or not isinstance(claim_text, str) or not claim_text:
        return ""
    try:
        matches = noun_matcher.find_in_text(claim_text)
    except Exception:
        return ""
    self_value = (
        _SELF_ENTITY_VALUE_FMT.format(self_player_id)
        if self_player_id is not None
        else None
    )
    best_start: Optional[int] = None
    best_axis: Optional[str] = None
    best_value: Optional[str] = None
    for m in matches:
        axis = getattr(m, "axis", "")
        if axis not in _HEARSAY_AXIS_TO_CUE_PREFIX:
            continue
        start = getattr(m, "start", 0)
        if best_start is None or start < best_start:
            best_start = start
            best_axis = axis
            best_value = getattr(m, "value", None)
    if best_axis is None or not best_value:
        return ""
    if best_axis == "entity":
        # P10: 人物対象は直接体験 cue (who = entity:actor:{id}) と同じトークン
        # 形式に揃え、同一人物の伝聞と直接体験が固着 shortlist で同じクラスタに
        # 寄るようにする。聞き手本人への言及は self: 軸へ分離する (P9)。
        actor_value = _to_direct_actor_value(best_value)
        if self_value is not None and best_value == self_value:
            return f"self:{actor_value}"
        return f"player:{actor_value}"
    return f"{_HEARSAY_AXIS_TO_CUE_PREFIX[best_axis]}:{best_value}"


def build_belief_evidence_cue_signature(episode: SubjectiveEpisode) -> str:
    """episode の構造化フィールドから決定論的な cue_signature を組む。

    - ``tool:<tool_name>`` (action が無ければ ``tool:none``): 必ず先頭
    - ``spot:<spot_id>``: ``location.spot_id`` があるときだけ追加
    - ``player:<相手>``: ``who`` の先頭要素があるときだけ追加
    """
    if not isinstance(episode, SubjectiveEpisode):
        raise TypeError("episode must be SubjectiveEpisode")

    parts: list[str] = []
    tool_name = episode.action.tool_name if episode.action is not None else None
    parts.append(f"tool:{tool_name}" if tool_name else f"tool:{_TOOL_NAME_UNKNOWN}")

    if episode.location.spot_id is not None:
        parts.append(f"spot:{episode.location.spot_id}")

    if episode.who:
        parts.append(f"player:{episode.who[0]}")

    return "|".join(parts)


def cue_tokens(cue_signature: str) -> tuple[str, ...]:
    """cue_signature を照合用トークン (軸の値部分、小文字化) に分解する。

    ``"tool:explore|spot:12|player:カイ"`` → ``("explore", "12", "カイ")``。
    ``:`` の後ろ (軸の値) だけを取り、軸名 (tool/spot/player) は落とす。
    固着パス (``belief_consolidation_coordinator._cue_tokens``) の shortlist
    照合と同じ規則を単一の実装に集約したもの (P3: CONFIRMATION 関連性ゲートが
    同じ照合を再利用するため)。
    """
    tokens: list[str] = []
    for part in cue_signature.split("|"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            _, _, value = part.partition(":")
            value = value.strip().lower()
        else:
            value = part.lower()
        if value:
            tokens.append(value)
    return tuple(tokens)


def belief_matches_cue_tokens(
    tags: tuple[str, ...], text: str, tokens: tuple[str, ...]
) -> bool:
    """belief の tags / text が cue トークンのいずれかと一致するか。

    固着 shortlist のスコアリングと同じ規則 (トークンが tag 集合に含まれる、
    または text に部分文字列として現れる) で「1 つでも一致すれば True」。
    P3 の CONFIRMATION ゲートはこれで「行動 context と関係する belief にだけ
    支持を積む」を判定する。tokens が空なら常に False (照合材料が無い)。
    """
    if not tokens:
        return False
    tag_set = {t.lower() for t in tags}
    text_lower = text.lower()
    return any(tok in tag_set or tok in text_lower for tok in tokens)


__all__ = [
    "build_belief_evidence_cue_signature",
    "build_hearsay_cue_signature",
    "cue_tokens",
    "belief_matches_cue_tokens",
]
