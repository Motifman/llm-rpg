#!/usr/bin/env python3
"""廃病院脱出ゲームデモ — 各プレイヤーの LLM プロンプトを完全可視化する。

目的:
  各プレイヤーが行動するたびに、全プレイヤーの「LLM に実際に渡されるプロンプト」を表示する。
  - 観測パイプラインが実際に動作し、他プレイヤーの行動が観測として蓄積される
  - 行動結果は ActionResultStore に記録される
  - SlidingWindowMemory に観測が蓄積される
  LLM は呼ばず、入出力の形を可視化するデバッグ用。
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root))

from ai_rpg_world.application.escape_game.escape_game_runtime import (
    EscapeGameRuntime,
    create_escape_game_runtime,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "abandoned_hospital.json"

DIVIDER = "=" * 72
THIN = "─" * 72


def show_player_prompt(runtime: EscapeGameRuntime, player_id: PlayerId) -> None:
    """1プレイヤー分の完全プロンプトを表示する。"""
    prompt = runtime.build_full_prompt(player_id)
    name = runtime.get_player_name(player_id)
    spot = runtime.get_player_spot_name(player_id)

    print(f"\n┌{'─' * 70}┐")
    print(f"│ {name} @ {spot}  (tick={runtime.current_tick()})".ljust(71) + "│")
    print(f"├{'─' * 70}┤")
    print(f"│ [SYSTEM PROMPT]".ljust(71) + "│")
    print(f"└{'─' * 70}┘")
    # Issue #227 後続 Step B: build_full_prompt の return shape を本家
    # DefaultPromptBuilder の {"messages": [...]} 形式に統一した。
    messages = prompt["messages"]
    system_content = messages[0]["content"]
    user_content = messages[1]["content"]

    for line in system_content.split("\n"):
        print(f"  {line}")

    print(f"\n  {'─' * 66}")
    print(f"  [USER MESSAGE]")
    print(f"  {'─' * 66}")
    for line in user_content.split("\n"):
        print(f"  {line}")

    print(f"\n  {'─' * 66}")
    print(f"  [AVAILABLE TOOLS] {', '.join(prompt['tools'])}")
    trc = prompt["tool_runtime_context"]
    if trc.targets:
        print(f"  [LABEL MAP]")
        for lbl, target in sorted(trc.targets.items()):
            parts = [f"kind={target.kind}"]
            if target.spot_id is not None:
                parts.append(f"spot_id={target.spot_id}")
            if target.world_object_id is not None:
                parts.append(f"obj_id={target.world_object_id}")
            if target.player_id is not None:
                parts.append(f"player_id={target.player_id}")
            if target.available_interactions:
                parts.append(f"actions={list(target.available_interactions)}")
            print(f"    {lbl}: {target.display_name} ({', '.join(parts)})")


def show_all_players_prompt(runtime: EscapeGameRuntime, player_ids: list, phase: str) -> None:
    """全プレイヤーのプロンプトを表示する。"""
    print(f"\n{'━' * 72}")
    print(f"  📍 {phase}")
    print(f"{'━' * 72}")
    for pid in player_ids:
        show_player_prompt(runtime, pid)


def show_action(name: str, description: str) -> None:
    print(f"\n{'▶' * 3} ACTION: {name} → {description}")


def show_result(messages: tuple) -> None:
    if messages:
        for m in messages:
            print(f"  ← {m}")


def main() -> None:
    print(f"{'━' * 72}")
    print("  廃病院脱出ゲームデモ — 各プレイヤーの LLM プロンプト完全可視化")
    print(f"{'━' * 72}")

    runtime = create_escape_game_runtime(SCENARIO_PATH)
    print(f"\nシナリオ: {runtime.metadata.title}")
    print(f"テーマ: {runtime.metadata.theme}")

    p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
    p2 = PlayerId(runtime.scenario.player_spawns[1].player_id)
    players = [p1, p2]

    # ── 初期状態 ──
    show_all_players_prompt(runtime, players, "初期状態（ゲーム開始直後）")

    # ── ユウキ: 受付の引き出しを調べる ──
    show_action("ユウキ", "interact(受付の引き出し, search)")
    r = runtime.do_interact(p1, "reception_desk", "search")
    show_result(r.messages)
    show_all_players_prompt(runtime, players, "ユウキが引き出しを調べた後")

    # ── マコト: ストレッチャーを調べる ──
    show_action("マコト", "interact(放置されたストレッチャー, examine)")
    r = runtime.do_interact(p2, "abandoned_stretcher", "examine")
    show_result(r.messages)

    # ── ユウキ: 廊下へ移動 ──
    show_action("ユウキ", "travel_to(薄暗い廊下)")
    runtime.do_move(p1, "dim_corridor")
    show_all_players_prompt(runtime, players, "ユウキが廊下に移動した後（P1離脱→P2に観測）")

    # ── ユウキ: ナースデスクを調べる ──
    show_action("ユウキ", "interact(ナースデスク, search)")
    r = runtime.do_interact(p1, "nurse_desk", "search")
    show_result(r.messages)

    # ── ユウキ: 院長室へ移動 ──
    show_action("ユウキ", "travel_to(院長室)")
    runtime.do_move(p1, "directors_office")

    # ── ユウキ: 書斎机を調べる → 日記入手 ──
    show_action("ユウキ", "interact(院長の書斎机, examine)")
    r = runtime.do_interact(p1, "directors_desk", "examine")
    show_result(r.messages)

    # ── ユウキ: 金庫を開ける → 非常口の鍵 ──
    show_action("ユウキ", "interact(壁埋め込みの金庫, open)")
    r = runtime.do_interact(p1, "office_safe", "open")
    show_result(r.messages)
    show_all_players_prompt(runtime, players, "ユウキが院長室で探索完了後")

    # ── マコト: 手術室へ移動 ──
    show_action("マコト", "travel_to(手術室)")
    runtime.do_move(p2, "operating_room")

    # ── マコト: 器具棚を調べる → メス入手 ──
    show_action("マコト", "interact(器具棚, search)")
    r = runtime.do_interact(p2, "instrument_shelf", "search")
    show_result(r.messages)

    # ── マコト: 地下室へ移動 ──
    show_action("マコト", "travel_to(地下室)")
    runtime.do_move(p2, "basement")

    # ── マコト: 壁の亀裂をメスで切り開く ──
    show_action("マコト", "interact(壁の亀裂, cut_open)")
    r = runtime.do_interact(p2, "wall_crack", "cut_open")
    show_result(r.messages)
    show_all_players_prompt(runtime, players, "マコトが地下室で亀裂を切り開いた後")

    # ── 合流して非常口へ ──
    show_action("ユウキ", "travel_to(非常口)")
    runtime.do_move(p1, "emergency_exit")
    show_action("マコト", "travel_to(隠し通路 → 非常口)")
    runtime.do_move(p2, "hidden_passage")
    runtime.do_move(p2, "emergency_exit")
    show_all_players_prompt(runtime, players, "非常口で合流")

    # ── 非常口の扉を開ける ──
    show_action("ユウキ", "interact(非常口の扉, unlock)")
    r = runtime.do_interact(p1, "emergency_door", "unlock")
    show_result(r.messages)

    # ── 脱出 ──
    show_action("ユウキ", "travel_to(外)")
    runtime.do_move(p1, "outside")
    show_action("マコト", "travel_to(外)")
    runtime.do_move(p2, "outside")

    # ── ゲーム終了 ──
    result = runtime.check_game_end()
    print(f"\n{'━' * 72}")
    print(f"  🏁 GAME END: {result.result} — {result.reason}")
    print(f"  最終ティック: {runtime.current_tick()}")
    print(f"{'━' * 72}")

    show_all_players_prompt(runtime, players, "ゲーム終了時（全行動の蓄積を確認）")


if __name__ == "__main__":
    main()
