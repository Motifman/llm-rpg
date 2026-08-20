"""保留中予測の再浮上 section 本文組み立て。"""

from typing import TYPE_CHECKING, Any, Optional

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder


def build_pending_predictions_text(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    being_id: BeingId,
    current_state_dto: Optional[Any],
) -> str:
    """U10a (予測誤差統一設計 部品6): pending prediction store から

    解決 cue が現在の状況と一致するものを再浮上させ、【保留中の予測】
    section 本体を組み立てる。

    以下のいずれかに該当すれば空文字を返す (= section ごと省略、flag OFF
    や機構未配線時は導入前と byte 一致する):
    - ``pending_prediction_store`` が未配線 (機構 OFF)
    - ``current_tick_provider`` が未注入 / 例外 / 非 int を返す
    - 一致する pending prediction が 0 件

    マッチング規則 (設計判断。詳細は PR 本文の不確実性欄を参照):
    - ``"spot:<id>"`` は現在の ``current_spot_id`` と一致するときだけ成立
    - ``"player:<name>"`` は現在同じ spot にいる (自分以外の) player の
      プロフィール名と完全一致するときだけ成立。episodic 受動想起の
      ``entity`` cue (内部 player_id ベース) とは独立の、pending
      prediction 専用の軽量マッチング (LLM が抽出時に書く名前は人間可読な
      表示名であり、内部 id 形式と直接比較できないため)
    - 1 件の pending の ``resolution_cues`` は **全件** 成立して初めて
      再浮上する (AND)。tick_from <= 現在 tick <= tick_to も必須
    - 決定論的な順序 (tick_from 昇順 → pending_id 昇順) で cap 件まで採用
    """
    if builder._pending_prediction_store is None:
        return ""
    if builder._current_tick_provider is None:
        return ""
    try:
        current_tick = builder._current_tick_provider()
    except Exception:
        builder._logger.debug(
            "current_tick_provider raised while resurfacing pending "
            "predictions; skipping",
            exc_info=True,
        )
        return ""
    if not isinstance(current_tick, int) or isinstance(current_tick, bool):
        return ""

    current_spot_id = (
        getattr(current_state_dto, "current_spot_id", None)
        if current_state_dto is not None
        else None
    )
    nearby_names: set[str] = set()
    other_player_ids = (
        getattr(current_state_dto, "current_player_ids", None) or ()
        if current_state_dto is not None
        else ()
    )
    for pid in other_player_ids:
        if int(pid) == int(player_id.value):
            continue
        try:
            other_profile = builder._profile_repository.find_by_id(PlayerId(int(pid)))
        except Exception:
            other_profile = None
        if other_profile is not None:
            nearby_names.add(other_profile.name.value)

    try:
        candidates = builder._pending_prediction_store.list_all_by_being(being_id)
    except Exception:
        builder._logger.warning(
            "pending_prediction_store.list_all_by_being failed; "
            "skipping resurfacing",
            exc_info=True,
        )
        return ""
    if not candidates:
        return ""

    def _cue_matches(cue: str) -> bool:
        if cue.startswith("spot:"):
            return current_spot_id is not None and cue[len("spot:"):] == str(
                current_spot_id
            )
        if cue.startswith("player:"):
            return cue[len("player:"):] in nearby_names
        return False

    matched = [
        p
        for p in candidates
        if p.tick_from <= current_tick <= p.tick_to
        and all(_cue_matches(c) for c in p.resolution_cues)
    ]
    if not matched:
        return ""
    matched.sort(key=lambda p: (p.tick_from, p.pending_id))
    selected = matched[: builder._pending_prediction_resurface_cap]

    recorder = builder._resolve_trace_recorder()
    if recorder is not None:
        try:
            recorder.record(
                TraceEventKind.PENDING_PREDICTION_RESURFACED,
                tick=current_tick,
                being_id=str(being_id.value),
                pending_ids=[p.pending_id for p in selected],
            )
        except Exception:
            builder._logger.debug(
                "trace recorder.record raised for "
                "PENDING_PREDICTION_RESURFACED; skipping",
                exc_info=True,
            )
    return "\n".join(f"・{p.text}" for p in selected)
