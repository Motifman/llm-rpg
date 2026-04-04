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


def show_full_prompt_with_memory(runtime: EscapeGameRuntime, player_id: PlayerId) -> None:
    """本番 DefaultPromptBuilder と同一フォーマットで記憶入りプロンプトを可視化する。

    デモでは DefaultPromptBuilder を直接使えない
    （WorldQueryService / PlayerProfileRepository 等のリポジトリ依存が必要）ため、
    各コンポーネントを個別に組み立てて同一の出力を再現する。
    """
    from datetime import datetime, timedelta
    from ai_rpg_world.application.observation.contracts.dtos import (
        ObservationEntry,
        ObservationOutput,
    )
    from ai_rpg_world.application.llm.contracts.dtos import (
        ActionResultEntry,
        EpisodeMemoryEntry,
    )
    from ai_rpg_world.application.llm.services.sliding_window_memory import (
        DefaultSlidingWindowMemory,
    )
    from ai_rpg_world.application.llm.services.action_result_store import (
        DefaultActionResultStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
        InMemoryEpisodeMemoryStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
        InMemoryLongTermMemoryStore,
    )
    from ai_rpg_world.application.llm.services.recent_events_formatter import (
        DefaultRecentEventsFormatter,
    )
    from ai_rpg_world.application.llm.services.predictive_memory_retriever import (
        DefaultPredictiveMemoryRetriever,
    )
    from ai_rpg_world.application.llm.services.context_format_strategy import (
        SectionBasedContextFormatStrategy,
    )

    now = datetime.now()

    # ── 1. 短期記憶: スライディングウィンドウに観測を注入 ──
    sliding_window = DefaultSlidingWindowMemory()
    observations = [
        ObservationEntry(
            occurred_at=now - timedelta(minutes=10),
            output=ObservationOutput(
                prose="受付の引き出しを調べたところ、院長室の鍵が見つかった。",
                structured={"type": "item_found", "item_name": "院長室の鍵", "spot_name": "エントランスホール"},
            ),
            game_time_label="深夜 0:05",
        ),
        ObservationEntry(
            occurred_at=now - timedelta(minutes=8),
            output=ObservationOutput(
                prose="マコトが「2階の手術室に何かありそうだ」と話している。",
                structured={"type": "speech_heard", "speaker": "マコト", "spot_name": "エントランスホール"},
            ),
            game_time_label="深夜 0:10",
        ),
        ObservationEntry(
            occurred_at=now - timedelta(minutes=6),
            output=ObservationOutput(
                prose="薄暗い廊下に到着した。消毒液の匂いが漂っている。",
                structured={"type": "arrived", "spot_name": "薄暗い廊下"},
            ),
            game_time_label="深夜 0:20",
        ),
        ObservationEntry(
            occurred_at=now - timedelta(minutes=4),
            output=ObservationOutput(
                prose="院長の書斎机から日記を見つけた。地下実験室に関する記述がある。",
                structured={"type": "item_found", "item_name": "院長の日記", "spot_name": "院長室"},
            ),
            game_time_label="深夜 0:35",
        ),
        ObservationEntry(
            occurred_at=now - timedelta(minutes=2),
            output=ObservationOutput(
                prose="金庫を開けると、非常口の鍵が入っていた。",
                structured={"type": "item_found", "item_name": "非常口の鍵", "spot_name": "院長室"},
            ),
            game_time_label="深夜 0:40",
        ),
    ]
    sliding_window.append_all(player_id, observations)

    # ── 2. 短期記憶: 行動結果ストアに結果を注入 ──
    action_store = DefaultActionResultStore()
    action_results = [
        ActionResultEntry(
            occurred_at=now - timedelta(minutes=10),
            action_summary="spot_graph_interact(受付の引き出し, search)",
            result_summary="成功: 院長室の鍵を入手した。",
        ),
        ActionResultEntry(
            occurred_at=now - timedelta(minutes=7),
            action_summary="spot_graph_travel_to(薄暗い廊下)",
            result_summary="成功: 薄暗い廊下に到着した。",
        ),
        ActionResultEntry(
            occurred_at=now - timedelta(minutes=5),
            action_summary="spot_graph_interact(院長の書斎机, examine)",
            result_summary="成功: 院長の日記を入手した。日記にはダイヤル番号のヒントが書かれている。",
        ),
        ActionResultEntry(
            occurred_at=now - timedelta(minutes=3),
            action_summary="spot_graph_interact(壁埋め込みの金庫, open)",
            result_summary="成功: 非常口の鍵を入手した。",
        ),
    ]
    for ar in action_results:
        action_store.append(
            player_id,
            action_summary=ar.action_summary,
            result_summary=ar.result_summary,
            occurred_at=ar.occurred_at,
        )

    # ── 3. 長期記憶: エピソードストアに過去の体験を注入 ──
    episode_store = InMemoryEpisodeMemoryStore()
    episodes = [
        EpisodeMemoryEntry(
            id="ep-001",
            context_summary="エントランスホールで受付の引き出しを調べた",
            action_taken="spot_graph_interact(受付の引き出し, search)",
            outcome_summary="院長室の鍵を入手した",
            entity_ids=("院長室の鍵", "受付の引き出し"),
            location_id="エントランスホール",
            timestamp=now - timedelta(minutes=10),
            importance="medium",
            surprise=False,
            recall_count=1,
            spot_id_value=1,
        ),
        EpisodeMemoryEntry(
            id="ep-002",
            context_summary="院長室で書斎机を調べたところ日記を発見。地下実験室について記述あり",
            action_taken="spot_graph_interact(院長の書斎机, examine)",
            outcome_summary="院長の日記を入手。ダイヤル番号のヒントが記載されていた",
            entity_ids=("院長の日記", "院長の書斎机", "地下実験室"),
            location_id="院長室",
            timestamp=now - timedelta(minutes=5),
            importance="high",
            surprise=False,
            recall_count=0,
            spot_id_value=4,
        ),
        EpisodeMemoryEntry(
            id="ep-003",
            context_summary="院長室の金庫を日記のヒントで開錠した",
            action_taken="spot_graph_interact(壁埋め込みの金庫, open)",
            outcome_summary="非常口の鍵を入手した",
            entity_ids=("非常口の鍵", "壁埋め込みの金庫"),
            location_id="院長室",
            timestamp=now - timedelta(minutes=3),
            importance="high",
            surprise=False,
            recall_count=0,
            spot_id_value=4,
        ),
    ]
    for ep in episodes:
        episode_store.add(player_id, ep)

    # ── 4. 長期記憶: 事実と法則を注入 ──
    long_term_store = InMemoryLongTermMemoryStore()
    long_term_store.add_fact(player_id, "受付の引き出しから院長室の鍵が見つかった")
    long_term_store.add_fact(player_id, "院長の日記に金庫のダイヤル番号のヒントが書かれていた")
    long_term_store.add_fact(player_id, "金庫の中に非常口の鍵が入っていた")
    long_term_store.add_fact(player_id, "鶴見博士は地下で延命研究を行っていた")

    long_term_store.upsert_law(player_id, subject="引き出し", relation="を search すると", target="鍵やアイテムが見つかることがある", delta_strength=2.0)
    long_term_store.upsert_law(player_id, subject="日記やメモ", relation="を読むと", target="パズルのヒントが得られる", delta_strength=3.0)
    long_term_store.upsert_law(player_id, subject="金庫", relation="は日記のヒントで", target="開錠できる", delta_strength=1.0)

    # ── 5. 各セクションをフォーマット ──
    ctx = runtime.build_llm_context(player_id)
    current_state_text = ctx.current_state_text

    recent_fmt = DefaultRecentEventsFormatter()
    recent_obs = sliding_window.get_recent(player_id, 20)
    recent_acts = action_store.get_recent(player_id, 20)
    recent_events_text = recent_fmt.format(recent_obs, recent_acts)

    retriever = DefaultPredictiveMemoryRetriever(
        episode_store=episode_store,
        long_term_store=long_term_store,
    )
    relevant_memories_text = retriever.retrieve_for_prediction(
        player_id,
        current_state_text,
        [d.name for d in runtime.get_tool_definitions()],
    )

    strategy = SectionBasedContextFormatStrategy()
    user_content = strategy.format(current_state_text, recent_events_text, relevant_memories_text)
    user_content = user_content.rstrip() + "\n\n利用可能なツールで次の行動を選んでください。"

    # ── 6. 完成した messages を表示 ──
    print(f"\n{'━' * 72}")
    print("  記憶入りプロンプトの完全可視化（DefaultPromptBuilder と同一フォーマット）")
    print(f"{'━' * 72}")

    system_content = runtime.build_system_prompt(player_id)
    print(f"\n{'=' * 72}")
    print("[messages[0]] role: system")
    print(f"{'=' * 72}")
    print(system_content)

    print(f"\n{'=' * 72}")
    print("[messages[1]] role: user")
    print(f"{'=' * 72}")
    print(user_content)

    print(f"\n{'─' * 72}")
    print("[参考] 各セクションの構成")
    print(f"{'─' * 72}")
    print("user メッセージは以下の 3 セクション + 行動指示で構成:")
    print("  1. ## 現在の状況      ← SpotGraphCurrentStateFormatter + UiContextBuilder")
    print("  2. ## 直近の出来事     ← ISlidingWindowMemory + IActionResultStore")
    print("  3. ## 関連する記憶     ← IPredictiveMemoryRetriever (エピソード + 事実 + 法則)")
    print("  4. 行動指示           ← 固定テキスト")
    print()
    print("[記憶パイプラインのデータフロー]")
    print("  観測バッファ drain → スライディングウィンドウ append")
    print("    ├→ get_recent(20件) → 「直近の出来事」セクション")
    print("    └→ overflow(溢れた古い観測) → RuleBasedMemoryExtractor")
    print("         └→ EpisodeMemoryEntry に変換 → IEpisodeMemoryStore に保存")
    print("              └→ リフレクション(定期) → ILongTermMemoryStore に事実・法則として昇格")
    print("  検索: DefaultPredictiveMemoryRetriever")
    print("    ├→ IEpisodeMemoryStore から現在地・ツール名で関連エピソード検索")
    print("    ├→ ILongTermMemoryStore から事実検索")
    print("    └→ ILongTermMemoryStore から法則検索")
    print("    → 「関連する記憶」セクションとして user メッセージに追加")


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

    # ── システムプロンプトの表示 ──
    print(f"\n{DIVIDER}")
    print("[SYSTEM PROMPT] 探索者A（ユウキ）")
    print(DIVIDER)
    print(runtime.build_system_prompt(p1))
    print(f"\n{DIVIDER}")
    print("[SYSTEM PROMPT] 探索者B（マコト）")
    print(DIVIDER)
    print(runtime.build_system_prompt(p2))

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
    # 記憶入りプロンプトの完全可視化
    # ═══════════════════════════════════════════
    show_full_prompt_with_memory(runtime, p1)


if __name__ == "__main__":
    main()
