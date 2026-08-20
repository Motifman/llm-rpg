"""予測フィードバック section の本文組み立て。"""

from datetime import datetime, timezone
from typing import Any, List

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry

_PREDICTION_FEEDBACK_FOLLOWUP_OBSERVATION_LIMIT = 2
# U0 (段0 台帳の N 件化): 直近 1 件だけだった【前回の予測と実際】を N 件の
# 台帳にする。値は「まず 3」(実装計画 §2 U0)。値を上げるほど過去の予測が
# 見えるが、後述の char cap と合わせて調整する前提の暫定値。
_PREDICTION_FEEDBACK_LEDGER_LIMIT = 3
# section 全体の総文字数 cap。超過した場合は古い entry から切り詰める
# (volatile section なので長くなりすぎると【直近の出来事】と重複がうるさく
# なる懸念があるため — 実装計画 §2 U0 の不確実性注記)。
_PREDICTION_FEEDBACK_TOTAL_CHAR_CAP = 900


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _nonempty_text(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def _collect_prediction_ledger_entries(
    action_results: List[ActionResultEntry],
) -> list[ActionResultEntry]:
    """expected_result を持つ action を新しい順に、直近 N 件だけ集める。"""

    predicted: list[ActionResultEntry] = []
    for entry in sorted(action_results, key=lambda e: _as_utc(e.occurred_at), reverse=True):
        if _nonempty_text(getattr(entry, "expected_result", None)) is not None:
            predicted.append(entry)
        if len(predicted) >= _PREDICTION_FEEDBACK_LEDGER_LIMIT:
            break
    return predicted


def _followups_for_prediction(
    observations: List[ObservationEntry],
    *,
    after: datetime,
    before: datetime | None,
) -> list[str]:
    """``after`` より後 (``before`` があればその前まで) の観測 prose を集める。

    entry ごとの後続観測の範囲を「次に新しい予測付き entry の occurred_at」で
    区切ることで、複数 entry の後続観測が重複しないようにする (``before`` が
    None のときは台帳中で最新の entry なので上限なし)。
    """
    followups: list[str] = []
    for obs in sorted(observations, key=lambda e: _as_utc(e.occurred_at)):
        occurred_at = _as_utc(obs.occurred_at)
        if occurred_at <= after:
            continue
        if before is not None and occurred_at >= before:
            continue
        prose = _nonempty_text(obs.output.prose)
        if prose is None:
            continue
        followups.append(prose)
        if len(followups) >= _PREDICTION_FEEDBACK_FOLLOWUP_OBSERVATION_LIMIT:
            break
    return followups


def _format_prediction_entry(
    entry: ActionResultEntry,
    expected: str,
    followups: list[str],
    *,
    is_pending: bool,
) -> list[str]:
    """台帳 1 件分を section の行リストにする。

    ``is_pending`` のときは結果がまだ判定できないとみなし予測行だけを
    出す (器を増やさず表示ロジックだけで「結果待ち」を表現する — 実装計画
    §2 U0)。「結果待ち」の判定は呼び出し側で行う (下記 build 参照)。
    """
    if is_pending:
        return [f"- 予測 (結果待ち): {expected}"]

    if not entry.success and entry.error_code is None:
        # 世界の外側で起きた失敗は、診断用の tool / status を本人の
        # 予測振り返りへ戻さない。空白があったという結果だけを残す。
        actual_parts = ["行動は実を結ばなかった"]
    else:
        tool = _nonempty_text(entry.tool_name) or "unknown_tool"
        status = "success=True" if entry.success else "success=False"
        actual_parts = [f"tool={tool}", status]
        if not entry.success and entry.error_code:
            actual_parts.append(f"error_code={entry.error_code}")
    result_summary = _nonempty_text(entry.result_summary)
    if result_summary is not None:
        actual_parts.append(f"result={result_summary}")

    lines = [
        f"- 予測: {expected}",
        f"- 実際: {' / '.join(actual_parts)}",
    ]
    if followups:
        lines.append("- 後続観測:")
        lines.extend(f"  - {text}" for text in followups)
    return lines


def build_prediction_feedback_text(
    action_results: List[ActionResultEntry],
    observations: List[ObservationEntry],
) -> str:
    """直近 N 件の予測付き action を、実際の結果と並べる prompt section 本文にする。

    U0 (段0 台帳の N 件化): 従来は最新 1 件だけだった台帳を直近
    ``_PREDICTION_FEEDBACK_LEDGER_LIMIT`` 件に広げる。

    選ぶ対象は最新側 N 件で、総文字数が
    ``_PREDICTION_FEEDBACK_TOTAL_CHAR_CAP`` を超える場合は古い方から
    切り詰める (= 最新側を優先して残す)。表示は選んだ分を古い順
    (時系列昇順、古い予測が上・最新が下) に並べる。同じプロンプト内の
    【直近の出来事】(recent_events_formatter) が時系列昇順で並ぶため、
    読み手の一貫性のために向きを揃える。もっとも新しい entry の帰結が
    まだ未確定なら「結果待ち」として予測だけを出す (古い順表示では
    最後の行に来る)。
    """

    if not isinstance(action_results, list):
        raise TypeError("action_results must be list")
    if not isinstance(observations, list):
        raise TypeError("observations must be list")
    for entry in action_results:
        if not isinstance(entry, ActionResultEntry):
            raise TypeError("action_results must contain only ActionResultEntry")
    for obs in observations:
        if not isinstance(obs, ObservationEntry):
            raise TypeError("observations must contain only ObservationEntry")

    ledger = _collect_prediction_ledger_entries(action_results)
    if not ledger:
        return ""

    entry_blocks: list[list[str]] = []
    for index, entry in enumerate(ledger):
        expected = _nonempty_text(entry.expected_result)
        # _collect_prediction_ledger_entries が非 None を保証するが、契約が
        # 将来壊れたとき assert では -O で無効化され「予測: None」が静かに
        # 出力される。静かな失敗を避けるため明示的に例外にする。
        if expected is None:
            raise ValueError(
                "prediction ledger entry lost its expected_result unexpectedly"
            )
        after = _as_utc(entry.occurred_at)
        before = _as_utc(ledger[index - 1].occurred_at) if index > 0 else None
        followups = _followups_for_prediction(observations, after=after, before=before)
        # 「結果待ち」= 本当にまだ結果が判明していない entry に限定する。
        # このワールドでは実行済み action は即座に success / error_code /
        # result_summary を持つため、それらは「結果が出た」とみなす。特に
        # 失敗 action (success=False) はその時点で予測が外れたことが確定した
        # 予測誤差そのものなので、後続観測が無くても隠さず「実際」を出す。
        # pending になるのは「最新 entry」かつ「後続観測が無い」かつ
        # 「成功したが result_summary も無い (= 帰結が本当に未確定)」場合のみ。
        is_pending = (
            index == 0
            and not followups
            and entry.success
            and _nonempty_text(entry.result_summary) is None
        )
        entry_blocks.append(
            _format_prediction_entry(entry, expected, followups, is_pending=is_pending)
        )

    header = "前回の予測を、願望ではなく世界への仮説として読み直してください。"
    # entry_blocks は最新順 (ledger と同じ)。cap は最新側を優先して残し、
    # 収まらなくなったら以降 (= より古い entry) を諦める。
    total_chars = len(header)
    selected_blocks: list[str] = []
    for block in entry_blocks:
        block_text = "\n".join(block)
        if selected_blocks and total_chars + len(block_text) + 1 > _PREDICTION_FEEDBACK_TOTAL_CHAR_CAP:
            break
        selected_blocks.append(block_text)
        total_chars += len(block_text) + 1
    # 表示は古い順 (時系列昇順)。【直近の出来事】と向きを揃えるため、
    # 最新順に選んだ blocks を反転してから並べる。
    lines = [header, *reversed(selected_blocks)]
    return "\n".join(lines)
