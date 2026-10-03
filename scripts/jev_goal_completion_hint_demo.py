"""過去 run の行動と結果に目的を当て、目的の達成の判断 (#1448) を実 Jev で測る。

過去の run には、本人が立てた目的を達成したのに申告しなかった場面が無い。goal store を
有効にした run はシナリオ目的が locked で、本人の goal_update は全件棄却されている。
そこで、棄却された goal_update の文を本人の目的とみなし、その後の本人の行動と結果に
当てて組み直す。ラベルは人が結果を読んで付けた (下の ``CASES``)。

- 行動の要約: trace の ``action`` の引数から、本番と同じ ``format_action_summary_for_display`` で作る
- 結果の文: trace の ``action_result`` の ``result_summary``。当時の run が末尾に付けていた
  【心の声】などと hint は、いまの結果の文には無いので切る
- 判断: 本番と同じ ``GoalCompletionHintService`` に目的を 1 件だけ持たせて問う

使い方:
    uv run python scripts/jev_goal_completion_hint_demo.py --runs-dir ../../../var/runs --out var/jev_goal_completion_hint/results.json
    uv run python scripts/jev_goal_completion_hint_demo.py --runs-dir ../../../var/runs --port stub
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_rpg_world.application.llm.ports.typed_judgment_port import (  # noqa: E402
    ITypedJudgmentPort,
)
from ai_rpg_world.application.llm.services.action_summary_format import (  # noqa: E402
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.goal_completion_hint_service import (  # noqa: E402
    GoalCompletionHintService,
)
from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (  # noqa: E402
    InMemoryGoalJournalStore,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (  # noqa: E402
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId  # noqa: E402
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (  # noqa: E402
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACTIVE,
    GoalEntry,
)


@dataclass(frozen=True)
class Case:
    run: str
    player_id: int
    tick: int
    goal_text: str
    achieved: bool
    why: str


CASES: tuple[Case, ...] = (
    Case('v4coop_memo_keep_004', 3, 61, '枯れ葉確保まで森方面を探索する。ノアと合流する。', True, '目的は枯れ葉の確保とノアとの合流で、合流は t57 に済んでおり、この結果で枯れ葉も確保できた'),
    Case('r1_003', 3, 60, '島の地形を把握し、山頂へのルートを見極める', True, '大樫に登って島の全容と川沿いに山頂へ至る道筋が見え、地形把握とルートの見極めが両方済んだ'),
    Case('v4coop_memo_hide_005', 3, 121, '大樫の樹で山頂へのルートを探す', True, '大樫の樹で山頂へのルートを探す目的に対し、結果で高地の泉を越えて山頂へ至る道筋が判明した'),
    Case('v4coop_reasonfirst_003', 1, 64, '手記と海図をカイとリオに渡し、全員でルート判断の材料を共有する。', True, '手記をカイ、海図をリオに渡す目的どおり、2件とも受け渡しが OK になった'),
    Case('v4coop_reasonfirst_003', 2, 18, '一旦カニのいる干潟を離れ、隠し入江で安全確保してから次の手を考える', True, '干潟を離れて隠し入江へ移る目的に対し、隠し入江への移動が成功した。「次の手を考える」は行動の完了条件ではないとみなした'),
    Case('v3coop_postrefactor_001', 4, 91, 'エイダ・ノアと合流して森の広場へ移動し、今夜の野営地を確保する', True, '森の広場へ移って野営地にする目的に対し、森の広場への移動が成功した。エイダ・ノアは先に広場へ向かっていた'),
    Case('v4coop_reasonfirst_003', 1, 186, '空腹100で倒れる前に、貝を生で食べてでも空腹を回復させる。その後リオやノアと合流して火起こしと山頂ルートの準備を進める。', True, '目的の中心である空腹の回復が、貝を食べて効果が適用されたことで済んだ。後段の合流と準備は「その後」の予定'),
    Case('v4coop_reasonfirst_003', 3, 197, '空腹を回復してから、焚き火を起こす手段を再検討する', True, '空腹を回復する目的に対し、貝を食べて効果が適用された。後段の再検討は「その後」の予定'),
    Case('v4coop_memo_keep_004', 4, 23, '枯れ葉を探す — 森の入口か川沿い。山頂ルートの確認も兼ねる。', True, 'メモの主題である枯れ葉探しが、枯れ葉の採集成功で済み、本人もその 2 tick 後に memo_done で完了にした'),
    Case('v4coop_memo_hide_005', 2, 44, '板切れに伝言を書いてから今夜は拠点で休む。明日の朝一番で枯れ葉を探しに行く。', False, '板切れに伝言を書く目的だが、書き込みが text 引数不足で拒否された'),
    Case('v4coop_reasonfirst_002', 2, 160, '山頂ルート確保・狼煙台で火を焚く', False, '狼煙台で火を焚く目的だが、点火は流木不足で拒否された'),
    Case('v4coop_reasonfirst_001', 3, 146, 'まず食料を確保してHPと空腹を回復させる。その後に山頂ルートを進む。', False, '食料で HP と空腹を回復する目的だが、食べた貝が腐っていてダメージを受けた'),
    Case('v3coop_stagnation_003', 2, 43, '枯れ葉を確保し、山頂への道を探す', False, '枯れ葉は確保したが、目的のもう半分である山頂への道は見つかっていない'),
    Case('v4coop_reasonfirst_003', 1, 103, '手記をカイに渡して朗読させ、川沿いか沼東かのルート確定の情報を得る。', False, '手記をカイに渡せたが、目的の本体である朗読させてルート情報を得ることはまだ起きていない'),
    Case('v4coop_distant_001', 2, 132, '一旦高地の泉でエイダと合流し、三人で山頂ルートの再確認と野犬対策を立てる', False, '高地の泉には着いたが、エイダとの合流と三人での作戦立ては結果に現れていない'),
    Case('v4coop_reasonfirst_003', 2, 33, 'リオ・カイと川沿いルートの下見に出発する。その前に空腹を抑えておく。', False, '目的は川沿いルートの下見に出発することで、空腹を抑えたのは「その前に」の準備段階にすぎない'),
    Case('v4coop_reasonfirst_002', 1, 33, 'リオと共に森の奥へ進み、枯れ葉確保と山頂ルートの発見を同時に狙う', False, '枯れ葉は見つけたが、同時に狙っていた山頂ルートの発見はまだ'),
    Case('v3coop_stagnation_001', 1, 163, 'カイと協力して干潟の岩陰で火を起こし、貝を焼いて食べる。その後、山頂ルートへ向かう。', False, '火を起こして貝を焼いて食べる目的に対し、貝を採っただけで火も食事もまだ'),
    Case('v3coop_postrefactor_001', 2, 193, 'エイダ蘇生 → 野犬対処 → リオ救出 → 山頂狼煙', False, '野犬は倒したが、目的は蘇生→野犬対処→リオ救出→山頂狼煙の連鎖で、救出と狼煙が残っている'),
    Case('v4coop_memo_hide_005', 4, 100, '夜明け前に動ける手がかりを掴みたい。仲間の声や獣の気配、川の音が聞こえれば方向の判断になる。', False, '仲間の声や獣の気配から手がかりを掴む目的だが、耳を澄ましても何も聞こえなかった'),
    Case('v4coop_0731_006', 3, 141, '海の見張りは飽和。あとは流木2本を山頂周辺か山道で確保し、狼煙を上げることに集中する', False, '流木 2 本を確保する目的だが、探索で何も見つからなかった'),
    Case('r1_003', 2, 157, '火床を組み、エイダから受け取った火打ち石で火を起こす', False, '火を起こす目的に対し、枯れ葉の採集すら拒否され、火も起きていない'),
    Case('v3coop_postrefactor_001', 4, 74, 'リオの手がかりを探すため、エイダとノアと連携して深い森かベリーの茂みを探索する', False, '目的はリオの手がかり探しで、釣りの失敗は目的と無関係な行動'),
)

_RESULT_SUFFIX_MARKERS = ("\n【", "\n\n[hint]")


def _action_and_result(case: Case, runs_dir: Path) -> tuple[str, str]:
    action: dict[str, Any] | None = None
    result: str | None = None
    with (runs_dir / case.run / "trace.jsonl").open(encoding="utf-8") as lines:
        for line in lines:
            event = json.loads(line)
            if event.get("tick") != case.tick or event.get("player_id") != case.player_id:
                continue
            payload = event.get("payload") or {}
            if event.get("kind") == "action" and action is None:
                action = payload
            elif event.get("kind") == "action_result" and result is None:
                result = str(payload.get("result_summary") or "")
    if action is None or result is None:
        raise LookupError(f"{case.run} t{case.tick} p{case.player_id}: action / action_result が無い")
    for marker in _RESULT_SUFFIX_MARKERS:
        result = result.split(marker, 1)[0]
    summary = format_action_summary_for_display(
        str(action.get("tool")), dict(action.get("arguments") or {})
    )
    return summary, result.strip()


def judge(case: Case, runs_dir: Path, port: ITypedJudgmentPort) -> dict[str, Any]:
    action_summary, result_summary = _action_and_result(case, runs_dir)
    being = BeingId(f"being_w1_p{case.player_id}")
    store = InMemoryGoalJournalStore()
    store.add_by_being(
        being,
        GoalEntry(
            goal_id=f"{case.run}_t{case.tick}_p{case.player_id}",
            player_id=case.player_id,
            text=case.goal_text,
            status=GOAL_STATUS_ACTIVE,
            locked=False,
            origin=GOAL_ORIGIN_SELF,
            created_tick=0,
            created_at=datetime.now(timezone.utc),
        ),
    )
    threshold = ResolvedLlmRuntimeConfig.for_tests().typed_judgment_goal_hint_min_probability
    detection = GoalCompletionHintService(
        store, judgment_port=port, min_probability=threshold
    ).detect(
        being, action_summary, result_summary
    )
    judgment = detection.judgments[0] if detection.judgments else None
    return {
        "case": f"{case.run}_t{case.tick}_p{case.player_id}",
        "achieved": case.achieved,
        "why": case.why,
        "goal": case.goal_text,
        "action": action_summary,
        "result": result_summary,
        "probability": None if judgment is None else round(judgment.probability, 4),
        "hinted": bool(detection.hints),
        "latency_ms": None if judgment is None else judgment.latency_ms,
        "unavailable_reason": detection.unavailable_reason,
    }


def _port(kind: str) -> ITypedJudgmentPort:
    if kind == "stub":
        from ai_rpg_world.application.llm.services.typed_judgment_stub import DeterministicTypedJudgmentPort
        return DeterministicTypedJudgmentPort()
    from dotenv import load_dotenv
    load_dotenv(); load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import create_typed_judgment_port_from_config
    port = create_typed_judgment_port_from_config(ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev"))
    assert port is not None
    return port


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--out", default="var/jev_goal_completion_hint/results.json")
    parser.add_argument("--port", choices=("jev", "stub"), default="jev")
    args = parser.parse_args(argv)
    port = _port(args.port)
    results = [judge(case, Path(args.runs_dir), port) for case in CASES]
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    for row in sorted(results, key=lambda r: -(r["probability"] or -1)):
        label = "達成" if row["achieved"] else "未達"
        print(f"{row['probability']!s:>7} {label} {row['case']} | {row['goal'][:30]} | {row['result'][:40]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
