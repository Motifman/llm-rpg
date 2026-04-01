#!/usr/bin/env python3
"""廃病院脱出ゲームデモ — 実 LLM パイプラインの出力を可視化する。

目的:
  1. LLM エージェントが実際に受け取る観測テキストを表示する
  2. LLM に渡されるツール定義（OpenAI tools 形式 JSON）を表示する
  3. ラベル→内部 ID のマッピング（ToolRuntimeContextDto）を表示する
  4. パズルフロー全体が動作することを検証する
  5. 情報の過不足を診断する
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root))

from demos.escape_game.escape_game_runtime import (
    EscapeGameRuntime,
    create_escape_game_runtime,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "abandoned_hospital.json"

DIVIDER = "=" * 72


def show_observation(runtime: EscapeGameRuntime, player_id: PlayerId, label: str) -> None:
    ctx = runtime.build_llm_context(player_id)
    name = runtime.get_player_name(player_id)
    print(f"\n{DIVIDER}")
    print(f"[OBSERVATION] {name} @ {runtime.get_player_spot_name(player_id)}  (tick={runtime.current_tick()})")
    print(DIVIDER)
    print(ctx.current_state_text)
    print()
    print("[LABEL → ID MAPPING]")
    for lbl, target in sorted(ctx.tool_runtime_context.targets.items()):
        parts = [f"kind={target.kind}"]
        if target.spot_id is not None:
            parts.append(f"spot_id={target.spot_id}")
        if target.world_object_id is not None:
            parts.append(f"object_id={target.world_object_id}")
        if target.location_area_id is not None:
            parts.append(f"sub_location_id={target.location_area_id}")
        if target.player_id is not None:
            parts.append(f"player_id={target.player_id}")
        if target.available_interactions:
            parts.append(f"actions={list(target.available_interactions)}")
        print(f"  {lbl}: {target.display_name} ({', '.join(parts)})")


def show_tools(runtime: EscapeGameRuntime) -> None:
    print(f"\n{DIVIDER}")
    print("[TOOL DEFINITIONS] (OpenAI tools format)")
    print(DIVIDER)
    for defn in runtime.get_tool_definitions():
        tool_json = {
            "type": "function",
            "function": {
                "name": defn.name,
                "description": defn.description,
                "parameters": defn.parameters,
            },
        }
        print(json.dumps(tool_json, ensure_ascii=False, indent=2))
        print()


def show_action(name: str, description: str) -> None:
    print(f"\n{'─' * 72}")
    print(f"[ACTION] {name}: {description}")
    print(f"{'─' * 72}")


def show_result(messages: tuple) -> None:
    if messages:
        for m in messages:
            print(f"  → {m}")


def main() -> None:
    print(f"{'━' * 72}")
    print("  廃病院脱出ゲームデモ — 実 LLM パイプライン出力の可視化")
    print(f"{'━' * 72}")

    runtime = create_escape_game_runtime(SCENARIO_PATH)
    print(f"\nシナリオ: {runtime.metadata.title}")
    print(f"テーマ: {runtime.metadata.theme}")
    print(f"推定ティック: {runtime.metadata.estimated_ticks}")

    p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
    p2 = PlayerId(runtime.scenario.player_spawns[1].player_id)

    # ── ツール定義の表示（1回だけ）──
    show_tools(runtime)

    # ── 初期状態の観測 ──
    show_observation(runtime, p1, "初期状態")
    show_observation(runtime, p2, "初期状態")

    # ═══════════════════════════════════════════
    # ゲームプレイ: 正解ルート
    # ═══════════════════════════════════════════

    # ── ユウキ: 受付の引き出しを調べる ──
    show_action("ユウキ", "spot_graph_interact(object_label='OBJ1', action_name='search')  [受付の引き出し]")
    r = runtime.do_interact(p1, "reception_desk", "search")
    show_result(r.messages)
    show_observation(runtime, p1, "引き出し調査後")

    # ── マコト: ストレッチャーを調べる ──
    show_action("マコト", "spot_graph_interact(object_label='OBJ1', action_name='examine')  [放置されたストレッチャー]")
    r = runtime.do_interact(p2, "abandoned_stretcher", "examine")
    show_result(r.messages)
    show_observation(runtime, p2, "ストレッチャー調査後")

    # ── ユウキ: 廊下へ移動 ──
    show_action("ユウキ", "spot_graph_travel_to(destination_label='S1')  [薄暗い廊下]")
    runtime.do_move(p1, "dim_corridor")
    show_observation(runtime, p1, "廊下到着")

    # ── ユウキ: ナースデスクを調べる ──
    show_action("ユウキ", "spot_graph_interact(object_label='OBJ1', action_name='search')  [ナースデスク]")
    r = runtime.do_interact(p1, "nurse_desk", "search")
    show_result(r.messages)

    # ── ユウキ: 院長室へ移動 ──
    show_action("ユウキ", "spot_graph_travel_to(destination_label='S...')  [院長室]")
    runtime.do_move(p1, "directors_office")
    show_observation(runtime, p1, "院長室到着")

    # ── ユウキ: 書斎机を調べる → 日記入手 ──
    show_action("ユウキ", "spot_graph_interact(object_label='OBJ..', action_name='examine')  [院長の書斎机]")
    r = runtime.do_interact(p1, "directors_desk", "examine")
    show_result(r.messages)

    # ── ユウキ: 金庫を開ける → 非常口の鍵 ──
    show_action("ユウキ", "spot_graph_interact(object_label='OBJ..', action_name='open')  [壁埋め込みの金庫]")
    r = runtime.do_interact(p1, "office_safe", "open")
    show_result(r.messages)
    show_observation(runtime, p1, "金庫開封後")

    # ── マコト: 手術室へ移動 ──
    show_action("マコト", "spot_graph_travel_to(destination_label='S...')  [手術室]")
    runtime.do_move(p2, "operating_room")

    # ── マコト: 器具棚を調べる → メス入手 ──
    show_action("マコト", "spot_graph_interact(object_label='OBJ..', action_name='search')  [器具棚]")
    r = runtime.do_interact(p2, "instrument_shelf", "search")
    show_result(r.messages)

    # ── マコト: 地下室へ移動 ──
    show_action("マコト", "spot_graph_travel_to(destination_label='S...')  [地下室]")
    runtime.do_move(p2, "basement")
    show_observation(runtime, p2, "地下室到着")

    # ── マコト: 壁の亀裂をメスで切り開く ──
    show_action("マコト", "spot_graph_interact(object_label='OBJ..', action_name='cut_open')  [壁の亀裂]")
    r = runtime.do_interact(p2, "wall_crack", "cut_open")
    show_result(r.messages)
    show_observation(runtime, p2, "亀裂切り開き後")

    # ── 合流して非常口へ ──
    show_action("ユウキ", "spot_graph_travel_to → 非常口")
    runtime.do_move(p1, "emergency_exit")
    show_observation(runtime, p1, "非常口到着")

    show_action("マコト", "spot_graph_travel_to → 隠し通路 → 非常口")
    runtime.do_move(p2, "hidden_passage")
    runtime.do_move(p2, "emergency_exit")
    show_observation(runtime, p2, "非常口到着（合流）")

    # ── 非常口の扉を開ける ──
    show_action("ユウキ", "spot_graph_interact(object_label='OBJ..', action_name='unlock')  [非常口の扉]")
    r = runtime.do_interact(p1, "emergency_door", "unlock")
    show_result(r.messages)

    # ── 脱出 ──
    show_action("ユウキ", "spot_graph_travel_to → 外")
    runtime.do_move(p1, "outside")
    show_observation(runtime, p1, "外（脱出！）")

    show_action("マコト", "spot_graph_travel_to → 外")
    runtime.do_move(p2, "outside")
    show_observation(runtime, p2, "外（脱出！）")

    # ── ゲーム終了判定 ──
    result = runtime.check_game_end()
    print(f"\n{'━' * 72}")
    print(f"[GAME END] {result.result} — {result.reason}")
    print(f"最終ティック: {runtime.current_tick()}")
    print(f"{'━' * 72}")

    # ═══════════════════════════════════════════
    # 診断: 情報粒度のレビュー
    # ═══════════════════════════════════════════
    print(f"\n{'━' * 72}")
    print("  診断: LLM に渡される情報の粒度レビュー")
    print(f"{'━' * 72}")
    print("""
[現在含まれている情報]
  ✓ 現在地の名前と説明文
  ✓ 雰囲気（明るさ・音・気温・匂い）
  ✓ 接続先（ラベル S1 等 + 名前 + 通行可否）
  ✓ オブジェクト（ラベル OBJ1 等 + 名前 + 操作候補の display_label と action_name）
  ✓ サブロケーション（ラベル SL1 等 + 名前 + 現在位置マーカー）
  ✓ 同スポットの他エンティティ（ラベル E1 等）
  ✓ ツール定義は destination_label / object_label / sub_location_label でラベル指定

[改善候補]
  △ 所持アイテム: 現在の観測に含まれていない → LLM が「鍵を持っているか」を判断できない
  △ ワールドフラグ: 読了フラグ等が観測に含まれていない → パズル進行状況がわからない
  △ エンティティ名: entity_id のみで名前がない → 「マコトがいる」と認識できない
  △ オブジェクト説明文: 現在はラベル行に名前のみ → 初見で何のオブジェクトか不明
  △ 接続先の通行条件: 「鍵が必要」等の条件テキストが表示されない
  △ 移動中の経過ティック表示: do_move 内で自動消化しているが実際は毎ティックの観測が必要
  △ speak/shout ツール: ツールカタログに未登録（現在は定義のみ）
""")


if __name__ == "__main__":
    main()
