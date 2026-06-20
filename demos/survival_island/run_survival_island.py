#!/usr/bin/env python3
"""漂流島サバイバル MVP デモ — シナリオが正しくロードされ動くかを確認するスモークテスト。

目的:
  - survival_island.json が既存ランタイム (world_runtime) でロードできる
  - 3 プレイヤー分のプロンプトが組み立てられる
  - 採取・移動・拠点での焚き火・狼煙までの happy path が動く

LLM は呼ばず、入出力の形と状態遷移を可視化する。
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root))

from ai_rpg_world.application.world_runtime.world_runtime import (  # noqa: E402
    WorldRuntime,
    create_world_runtime,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId  # noqa: E402
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (  # noqa: E402
    InteractionNotAllowedException,
)

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "survival_island.json"
)


def show_player_brief(runtime: WorldRuntime, player_id: PlayerId) -> None:
    """1 プレイヤーの簡易状態を表示する (システムプロンプトは長いので省略)。"""
    name = runtime.get_player_name(player_id)
    spot = runtime.get_player_spot_name(player_id)
    prompt = runtime.build_full_prompt(player_id)
    user_content = prompt["messages"][1]["content"]
    print(f"\n┌─── {name} @ {spot}  (tick={runtime.current_tick()}) ───")
    for line in user_content.split("\n"):
        print(f"│ {line}")
    print(f"└─── tools: {', '.join(prompt['tools'])}")


def show_action(actor: str, desc: str) -> None:
    print(f"\n▶▶▶ {actor}: {desc}")


def show_result(messages) -> None:
    if messages:
        for m in messages:
            print(f"  ← {m}")


def main() -> None:
    print("━" * 72)
    print("  漂流島サバイバル MVP — シナリオロードと happy path スモークテスト")
    print("━" * 72)

    runtime = create_world_runtime(SCENARIO_PATH)
    print(f"\nシナリオ: {runtime.metadata.title}")
    print(f"テーマ: {runtime.metadata.theme}")
    print(f"目標 tick 数: {runtime.metadata.estimated_ticks}")

    mira = PlayerId(runtime.scenario.player_spawns[0].player_id)
    ren = PlayerId(runtime.scenario.player_spawns[1].player_id)
    toma = PlayerId(runtime.scenario.player_spawns[2].player_id)

    # ── 初期状態: 全員浜辺 ──
    print("\n" + "━" * 72)
    print("  初期状態（全員 難破船の浜）")
    print("━" * 72)
    for pid in (mira, ren, toma):
        show_player_brief(runtime, pid)

    # ── ミラ: 船倉を漁る → ナイフと蔓ロープ ──
    show_action("ミラ", "船倉を漁る")
    r = runtime.do_interact(mira, "wreck_hold", "search")
    show_result(r.messages)

    # ── ミラ: 流木を拾う ──
    show_action("ミラ", "流木を拾う")
    r = runtime.do_interact(mira, "driftwood_pile", "gather")
    show_result(r.messages)

    # ── レン: 拠点へ移動 → 椰子のために森の入口へ ──
    show_action("レン", "拠点へ移動")
    runtime.do_move(ren, "campsite")
    show_action("レン", "森の入口へ移動")
    runtime.do_move(ren, "forest_edge")
    show_action("レン", "椰子の実を拾う")
    r = runtime.do_interact(ren, "coconut_palm", "gather_coconut")
    show_result(r.messages)

    # ── トマ: 隠し入江へ向かい火打ち石と枯れ葉を回収 ──
    show_action("トマ", "干潟へ移動")
    runtime.do_move(toma, "tidal_pools")
    show_action("トマ", "隠し入江へ移動")
    runtime.do_move(toma, "hidden_cove")
    show_action("トマ", "砂に埋もれた箱を開ける")
    r = runtime.do_interact(toma, "buried_chest", "open_chest")
    show_result(r.messages)

    # ── 拠点合流 ──
    show_action("ミラ", "拠点へ移動")
    runtime.do_move(mira, "campsite")
    show_action("トマ", "拠点へ復路 (入江 → 干潟 → 浜辺 → 拠点)")
    runtime.do_move(toma, "tidal_pools")
    runtime.do_move(toma, "shipwreck_beach")
    runtime.do_move(toma, "campsite")
    show_action("レン", "拠点へ復路 (入口 → 拠点)")
    runtime.do_move(ren, "campsite")

    print("\n" + "━" * 72)
    print("  拠点合流 (tick=" + str(runtime.current_tick()) + ")")
    print("━" * 72)
    for pid in (mira, ren, toma):
        show_player_brief(runtime, pid)

    # ── 焚き火を起こすには流木+枯れ葉+火打ち石が必要。
    #    流木はミラ、枯れ葉と火打ち石はトマが持っている。一人で着火できない。
    show_action("トマ", "焚き火を起こす (流木が無いので失敗するはず)")
    try:
        r = runtime.do_interact(toma, "fire_pit", "build_fire")
        show_result(r.messages)
    except InteractionNotAllowedException as e:
        print(f"  ✗ 期待通り失敗: {e}")

    # ── Phase 2 (#PR-B) で導入した drop/pickup を使って素材を集約する ──
    print("\n" + "━" * 72)
    print("  3 人協力: ミラの流木 + トマの火打ち石/枯れ葉 を 1 人に集約する")
    print("━" * 72)

    # ミラのインベントリスロットを確認
    mira_inv = runtime._player_inventory_repo.find_by_id(mira)
    mira_driftwood_slot = None
    for slot in range(mira_inv._max_slots):
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId
        iid = mira_inv.get_item_instance_id_by_slot(SlotId(slot))
        if iid is not None:
            item = runtime._item_repo.find_by_id(iid)
            if item and item.item_spec.name == "流木":
                mira_driftwood_slot = slot
                break
    assert mira_driftwood_slot is not None, "ミラが流木を持っていない (テスト前提崩壊)"

    show_action("ミラ", f"流木 (slot {mira_driftwood_slot}) を拠点の地面に置く")
    r = runtime.do_drop_item(mira, mira_driftwood_slot)
    show_result(r.messages)

    # トマの新プロンプトで以下 2 つを確認:
    # (1) 地面アイテムセクション (G1) が見える
    # (2) 直近の出来事に「ミラが流木を地面に置いた」が同室観測として届いている
    print("\n  --- トマ視点 (drop 直後): G1 と同室観測の両方が出るか ---")
    show_player_brief(runtime, toma)

    # レンは同室なので同じ観測が届くはず
    print("\n  --- レン視点 (同室・離れていない): 同じ observation が届いているか ---")
    show_player_brief(runtime, ren)

    # 地面アイテム一覧をトマ視点で確認
    ground = runtime.list_ground_items_at_player_spot(toma)
    print(f"\n  [拠点の地面] {len(ground)} 個のアイテム:")
    for g in ground:
        spec = runtime._item_spec_repo.find_by_id(g.item_spec_id)
        spec_obj = spec.to_item_spec() if hasattr(spec, "to_item_spec") else spec
        print(f"    - {spec_obj.name} (instance_id={g.item_instance_id.value})")

    show_action("トマ", "地面の流木を拾う")
    r = runtime.do_pickup_item(toma, ground[0].item_instance_id.value)
    show_result(r.messages)

    show_action("トマ", "焚き火を起こす (流木 + 火打ち石 + 枯れ葉 が揃ったので成功するはず)")
    try:
        r = runtime.do_interact(toma, "fire_pit", "build_fire")
        show_result(r.messages)
        print("  ✓ 3 人協力で焚き火着火に成功 (drop / pickup 経路)")
    except InteractionNotAllowedException as e:
        print(f"  ✗ 想定外: {e}")

    # ── give ツールも使える事を確認 (Phase A 追加) ──
    # トマが焼ける魚を持っていない状態で、ミラが手元の蔓ロープを直接トマに渡す。
    # drop → pickup の 2 アクションが 1 つに圧縮される。
    print("\n" + "━" * 72)
    print("  give ツール: ミラがトマに直接アイテムを渡す (drop+pickup の圧縮)")
    print("━" * 72)
    mira_inv = runtime._player_inventory_repo.find_by_id(mira)
    vine_slot = None
    from ai_rpg_world.domain.player.value_object.slot_id import SlotId
    for slot in range(mira_inv._max_slots):
        iid = mira_inv.get_item_instance_id_by_slot(SlotId(slot))
        if iid is None:
            continue
        item = runtime._item_repo.find_by_id(iid)
        if item and item.item_spec.name == "蔓のロープ":
            vine_slot = slot
            break
    if vine_slot is not None:
        show_action("ミラ", f"蔓ロープ (slot {vine_slot}) をトマに直接渡す")
        try:
            r = runtime._item_transfer_service.give_item(
                mira, toma, SlotId(vine_slot)
            )
            show_result(r.messages)

            toma_inv = runtime._player_inventory_repo.find_by_id(toma)
            owned_names = []
            for s in range(toma_inv._max_slots):
                iid = toma_inv.get_item_instance_id_by_slot(SlotId(s))
                if iid:
                    item = runtime._item_repo.find_by_id(iid)
                    if item:
                        owned_names.append(item.item_spec.name)
            print(f"  ✓ トマの所持: {owned_names}")
            print("  (レンの直近の出来事に '蔓のロープをトマに渡した' が観測されるはず)")
            show_player_brief(runtime, ren)
        except Exception as e:
            print(f"  ✗ 想定外: {e}")
    else:
        print("  (ミラが蔓ロープを持っていないので give のスキップ)")

    # ── ステルス drop の実演 (Phase C: witness_policy=ACTOR_ONLY) ──
    # ミラが拠点で「こっそり」流木を地面に置く。同室にトマとレンが居ても、
    # 観測ログには現れない (recipient strategy が空集合を返すため)。
    print("\n" + "━" * 72)
    print("  ステルス drop (Phase C): こっそり置けば誰も気づかない")
    print("━" * 72)
    # ミラに新しい流木を取らせる
    runtime.do_move(mira, "shipwreck_beach")
    runtime.advance_tick()
    runtime.advance_tick()
    runtime.advance_tick()
    runtime.advance_tick()
    runtime.do_interact(mira, "driftwood_pile", "gather")
    runtime.do_move(mira, "campsite")

    mira_inv = runtime._player_inventory_repo.find_by_id(mira)
    stealth_slot = None
    for slot in range(mira_inv._max_slots):
        iid = mira_inv.get_item_instance_id_by_slot(SlotId(slot))
        if iid is None:
            continue
        item = runtime._item_repo.find_by_id(iid)
        if item and item.item_spec.name == "流木":
            stealth_slot = slot
            break

    if stealth_slot is not None:
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy

        # 事前にレンが観測している「ミラの drop」イベント数を数える
        def _count_mira_drops(player_id) -> int:
            content = runtime.build_full_prompt(player_id)["messages"][1]["content"]
            return sum(
                1 for line in content.split("\n")
                if "ミラ(隊長)が流木を地面に置いた" in line
            )

        before_ren = _count_mira_drops(ren)
        before_toma = _count_mira_drops(toma)

        show_action(
            "ミラ",
            f"流木 (slot {stealth_slot}) を **こっそり** 地面に置く (stealth=True)",
        )
        r = runtime._item_transfer_service.drop_item(
            mira, SlotId(stealth_slot),
            witness_policy=WitnessPolicy.ACTOR_ONLY,
        )
        show_result(r.messages)

        after_ren = _count_mira_drops(ren)
        after_toma = _count_mira_drops(toma)

        print(
            f"  レンの観測件数 (ミラの drop): {before_ren} → {after_ren}"
        )
        print(
            f"  トマの観測件数 (ミラの drop): {before_toma} → {after_toma}"
        )
        if after_ren == before_ren and after_toma == before_toma:
            print("  ✓ ステルス drop 成功: 同室者の観測件数は増えなかった")
        else:
            print("  ✗ 想定外: 観測が漏れた")
    else:
        print("  (ミラの流木が見つからずスキップ)")

    # ── 数ティック空回しして reactive_bindings の動作を観察 ──
    print("\n" + "━" * 72)
    print("  数ティック経過 (待機) — リソース再生の挙動を観察")
    print("━" * 72)
    for _ in range(10):
        runtime.advance_tick()
    print(f"現在 tick: {runtime.current_tick()}")

    # ── ミラ: もう一度流木を拾えるか (4 tick で再生のはず) ──
    show_action("ミラ", "難破船の浜へ戻る")
    runtime.do_move(mira, "shipwreck_beach")
    show_action("ミラ", "再び流木を拾う (再生済みのはず)")
    try:
        r = runtime.do_interact(mira, "driftwood_pile", "gather")
        show_result(r.messages)
        print("  ✓ 再生確認 OK")
    except InteractionNotAllowedException as e:
        print(f"  ✗ 想定外: 再生失敗 — {e}")

    # ── 終了 ──
    result = runtime.check_game_end()
    print("\n" + "━" * 72)
    print(f"  🏁 状態: {result}")
    print(f"  最終 tick: {runtime.current_tick()}")
    print("━" * 72)


if __name__ == "__main__":
    main()
