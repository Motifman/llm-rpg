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


__all__ = ["build_belief_evidence_cue_signature"]
