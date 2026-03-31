"""廃病院脱出ゲーム — デモ実行スクリプト。

正解ルートをプログラム的に実行しながら、各ステップで
LLM エージェントが受け取る観測・プロンプト・ツール一覧を表示する。

Usage:
    source venv/bin/activate
    python -m demos.escape_game.run_escape_game
"""

from __future__ import annotations

import sys
from pathlib import Path

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT / "data" / "scenarios" / "abandoned_hospital.json"


def _sep(title: str = "") -> str:
    if title:
        return f"\n{'━' * 20} {title} {'━' * 20}"
    return f"\n{'━' * 60}"


def main() -> None:
    from demos.escape_game.escape_game_runtime import create_escape_game_runtime

    print(_sep("廃病院からの脱出 ―― 白鷺病院の記憶"))
    print("シナリオを読み込んでいます...")

    runtime = create_escape_game_runtime(SCENARIO_PATH)
    meta = runtime.metadata
    print(f"  タイトル: {meta.title}")
    print(f"  テーマ: {meta.theme}")
    print(f"  難易度: {meta.difficulty}")
    print(f"  推定ティック: {meta.estimated_ticks}")
    print(f"  プレイヤー数: {len(runtime.scenario.player_spawns)}")
    for p in runtime.scenario.player_spawns:
        pid = PlayerId(p.player_id)
        print(f"    {p.name} → {runtime.get_player_spot_name(pid)}")

    p1 = PlayerId(runtime.scenario.player_spawns[0].player_id)
    p2 = PlayerId(runtime.scenario.player_spawns[1].player_id)

    # ── 初期状態の表示 ──

    print(_sep("初期状態: 探索者A（ユウキ）"))
    print("\n[SYSTEM PROMPT]")
    print(runtime.build_system_prompt(p1))
    print("\n[OBSERVATION]")
    print(runtime.build_observation(p1))
    print("\n[AVAILABLE TOOLS]")
    print(runtime.build_available_tools(p1))

    print(_sep("初期状態: 探索者B（マコト）"))
    print("\n[OBSERVATION]")
    print(runtime.build_observation(p2))
    print("\n[AVAILABLE TOOLS]")
    print(runtime.build_available_tools(p2))

    # ── ゲームプレイ: 正解ルート ──

    def step(title: str) -> None:
        runtime.advance_tick()
        print(_sep(f"Tick {runtime.current_tick()}: {title}"))

    def show_result(player: PlayerId, result_msgs, label: str = "ACTION RESULT") -> None:
        name = runtime.get_player_name(player)
        print(f"\n[{label} — {name}]")
        for msg in result_msgs:
            print(f"  {msg}")

    def show_obs(player: PlayerId) -> None:
        name = runtime.get_player_name(player)
        print(f"\n[OBSERVATION — {name}]")
        print(runtime.build_observation(player))
        print(f"\n[AVAILABLE TOOLS — {name}]")
        print(runtime.build_available_tools(player))

    # ════════════════════════════════════════════════════
    # ゲームプレイ: 正解ルート（ユウキ=鍵・パズル担当、マコト=道具・探索担当）
    # ════════════════════════════════════════════════════

    # ── ユウキ: 受付で院長室の鍵を入手 ──
    step("ユウキ: 受付の引き出しを調べる → 院長室の鍵")
    r = runtime.do_interact(p1, "reception_desk", "search")
    show_result(p1, r.messages)
    show_obs(p1)

    # ── マコト: 放置されたストレッチャーを調べる（雰囲気アイテム） ──
    step("マコト: ストレッチャーを調べる → 割れた注射器（ロアアイテム）")
    r = runtime.do_interact(p2, "abandoned_stretcher", "examine")
    show_result(p2, r.messages)
    show_obs(p2)

    # ── ユウキ: 廊下へ移動 → ナースデスクで手術記録簿を入手 ──
    step("ユウキ: 廊下へ移動")
    runtime.do_move(p1, "dim_corridor")
    show_obs(p1)

    step("ユウキ: ナースデスクを調べる → 手術記録簿")
    r = runtime.do_interact(p1, "nurse_desk", "search")
    show_result(p1, r.messages)
    show_obs(p1)

    # ── ユウキ: 院長室へ移動（鍵あり） → 日記入手 → 金庫を開ける ──
    step("ユウキ: 院長室へ移動（院長室の鍵を使用）")
    runtime.do_move(p1, "directors_office")
    show_obs(p1)

    step("ユウキ: 院長の書斎机を調べる → 日記+read_diaryフラグ")
    r = runtime.do_interact(p1, "directors_desk", "examine")
    show_result(p1, r.messages)
    show_obs(p1)

    step("ユウキ: 金庫を開ける（暗証番号1987: 日記+手術記録から推理）→ 非常口の鍵")
    r = runtime.do_interact(p1, "office_safe", "open")
    show_result(p1, r.messages)
    show_obs(p1)

    # ── マコト: 手術室で道具を集める ──
    step("マコト: 手術室に移動")
    runtime.do_move(p2, "operating_room")
    show_obs(p2)

    step("マコト: 器具棚の奥を探る → 錆びたメス入手")
    r = runtime.do_interact(p2, "instrument_shelf", "search")
    show_result(p2, r.messages)
    show_obs(p2)

    # ── マコト: 地下ルートを開拓（メスで亀裂を広げる） ──
    step("マコト: 地下室に移動")
    runtime.do_move(p2, "basement")
    show_obs(p2)

    step("マコト: 壁の亀裂をメスで広げる → 隠し通路出現")
    r = runtime.do_interact(p2, "wall_crack", "cut_open")
    show_result(p2, r.messages)
    show_obs(p2)

    # ── 合流して非常口へ ──
    step("ユウキ: 非常口に移動（廊下→非常階段経由）")
    runtime.do_move(p1, "emergency_exit")
    show_obs(p1)

    step("マコト: 非常口に移動（隠し通路経由）")
    runtime.do_move(p2, "hidden_passage")
    runtime.do_move(p2, "emergency_exit")
    show_obs(p2)

    # ── ユウキ: 非常口の扉を開ける ──
    step("ユウキ: 非常口の鍵で扉を開ける")
    r = runtime.do_interact(p1, "emergency_door", "unlock")
    show_result(p1, r.messages)
    show_obs(p1)

    # ── 脱出！ ──
    step("ユウキ: 外に出る！")
    runtime.do_move(p1, "outside")
    show_obs(p1)

    step("マコト: 外に出る！")
    runtime.do_move(p2, "outside")
    show_obs(p2)

    # ── ゲーム終了判定 ──
    end = runtime.check_game_end()
    print(_sep("ゲーム終了判定"))
    print(f"  終了: {end.is_ended}")
    print(f"  結果: {end.result}")
    print(f"  理由: {end.reason}")

    # ── アクション履歴のサマリー ──
    print(_sep("アクション履歴"))
    for rec in runtime.history:
        detail = f"[Tick {rec.tick}] {rec.player_name}: {rec.action_type} — {rec.action_detail}"
        if rec.result_messages:
            detail += f"  → {rec.result_messages[0][:60]}..."
        print(f"  {detail}")

    print(_sep())
    if end.is_ended and end.result and end.result.name == "WIN":
        print("🎉 脱出成功！ 白鷺病院の悪夢は終わった。")
    else:
        print("💀 脱出失敗...")
    print()


if __name__ == "__main__":
    main()
