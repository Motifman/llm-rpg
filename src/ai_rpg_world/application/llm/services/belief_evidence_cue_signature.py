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

from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

_TOOL_NAME_UNKNOWN = "none"


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
    "cue_tokens",
    "belief_matches_cue_tokens",
]
