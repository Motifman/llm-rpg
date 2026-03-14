#!/usr/bin/env python3
"""
LLM マルチターンループのプロンプト検証用デモスクリプト。

実際の LLM API を呼ばず、観測→思考→行動→結果のループをシミュレートし、
各ターンで LLM に渡されるプロンプト（入力）と、シミュレートされた出力を表示する。
前ターンの観測・行動・結果が次ターンのプロンプトに正しく反映されているかを確認できる。

使い方:
    cd /path/to/ai_rpg_world
    source venv/bin/activate
    python scripts/demo_llm_multiturn_prompt_inspection.py           # デフォルト3ターン
    python scripts/demo_llm_multiturn_prompt_inspection.py -n 5    # 5ターン実行
    python scripts/demo_llm_multiturn_prompt_inspection.py -o out.txt  # ファイル出力
"""

import argparse
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.current_state_formatter import (
    DefaultCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.system_prompt_builder import (
    DefaultSystemPromptBuilder,
)
from ai_rpg_world.application.llm.services.tool_catalog import (
    register_default_tools,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import Role
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
    PhysicalMapAggregate,
)
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import (
    DirectionEnum,
    ObjectTypeEnum,
)
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
    InMemorySpotRepository,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
)


def _create_profile(
    player_id: int, name: str = "TestPlayer", role: Role = Role.CITIZEN
) -> PlayerProfileAggregate:
    return PlayerProfileAggregate.create(
        player_id=PlayerId(player_id),
        name=PlayerName(name),
        role=role,
    )


def _setup_components(
    data_store: Optional[InMemoryDataStore] = None,
) -> Tuple[DefaultPromptBuilder, Dict[str, Any]]:
    """PromptBuilder と各種コンポーネントをセットアップする。"""
    ds = data_store or InMemoryDataStore()
    ds.clear_all()
    profile_repo = InMemoryPlayerProfileRepository(ds)
    status_repo = InMemoryPlayerStatusRepository(ds)
    phys_repo = InMemoryPhysicalMapRepository(ds)
    spot_repo = InMemorySpotRepository(ds)
    spot_repo.save(Spot(SpotId(1), "Default", "草原エリア"))
    spot_repo.save(Spot(SpotId(2), "隣のエリア", "草原が広がる"))

    connected = GatewayBasedConnectedSpotsProvider(phys_repo)
    world_query = WorldQueryService(
        player_status_repository=status_repo,
        player_profile_repository=profile_repo,
        physical_map_repository=phys_repo,
        spot_repository=spot_repo,
        connected_spots_provider=connected,
    )
    buffer = DefaultObservationContextBuffer()
    sliding = DefaultSlidingWindowMemory()
    action_store = DefaultActionResultStore()
    formatter = DefaultCurrentStateFormatter()
    recent_formatter = DefaultRecentEventsFormatter()
    strategy = SectionBasedContextFormatStrategy()
    system_builder = DefaultSystemPromptBuilder()
    registry = DefaultGameToolRegistry()
    register_default_tools(registry)
    tools_provider = DefaultAvailableToolsProvider(registry)

    prompt_builder = DefaultPromptBuilder(
        observation_buffer=buffer,
        sliding_window_memory=sliding,
        action_result_store=action_store,
        world_query_service=world_query,
        player_profile_repository=profile_repo,
        current_state_formatter=formatter,
        recent_events_formatter=recent_formatter,
        context_format_strategy=strategy,
        system_prompt_builder=system_builder,
        available_tools_provider=tools_provider,
    )

    repos = {
        "profile_repo": profile_repo,
        "status_repo": status_repo,
        "phys_repo": phys_repo,
        "spot_repo": spot_repo,
        "buffer": buffer,
        "action_store": action_store,
    }
    return prompt_builder, repos


def _add_observation(
    buffer: DefaultObservationContextBuffer,
    player_id: PlayerId,
    prose: str,
    structured: Optional[Dict[str, Any]] = None,
    game_time_label: Optional[str] = None,
) -> None:
    entry = ObservationEntry(
        occurred_at=datetime.now(),
        output=ObservationOutput(
            prose=prose,
            structured=structured or {},
            observation_category="environment",
            schedules_turn=True,
            breaks_movement=False,
        ),
        game_time_label=game_time_label,
    )
    buffer.append(player_id, entry)


# シナリオ: (観測リスト (prose, game_time_label), ツール名, 行動要約, 結果要約)
# game_time_label はゲーム内時刻。None のときはタイムスタンプなし。
DEFAULT_TURN_SCENARIO: List[
    Tuple[List[Tuple[str, Optional[str]]], str, str, str]
] = [
    # ターン1: 初期観測 → 移動を決意
    (
        [
            ("東方向に草原が広がっている。風が心地よい。", "1年1月1日 朝"),
            ("遠くに人影が見えた。", "1年1月1日 朝"),
        ],
        TOOL_NAME_MOVE_TO_DESTINATION,
        "move_to_destination({\"destination_spot_id\": 2}) を実行しました。",
        "移動を開始しました。Default から隣のエリアへ向かっています。",
    ),
    # ターン2: 到着観測 → 待機
    (
        [
            ("隣のエリアに到着した。穏やかな草原だ。", "1年1月1日 昼"),
            ("先ほどの人影は見えない。", "1年1月1日 昼"),
        ],
        TOOL_NAME_NO_OP,
        "world_no_op({}) を実行しました。",
        "周囲を観察し、様子をうかがうことにした。",
    ),
    # ターン3: 追加観測 → 再び移動の意志
    (
        [("北西に小さな村の影が見える。", "1年1月1日 夕")],
        TOOL_NAME_NO_OP,
        "world_no_op({}) を実行しました。",
        "今日はここまでにして、明日村に向かうことにした。",
    ),
]


def _print_turn_result(
    turn_index: int,
    request: Dict[str, Any],
    simulated_output: Dict[str, str],
    output_file=None,
) -> None:
    """1ターン分の入出力を整形して出力する。"""

    def out(s: str = "") -> None:
        dst = output_file or sys.stdout
        print(s, file=dst)

    sep = "=" * 80
    out(f"\n{sep}")
    out(f"【ターン {turn_index}】LLM への入力・シミュレート出力")
    out(sep)

    # --- 入力（プロンプト）---
    out("\n■ 入力（プロンプト）")
    out("-" * 40)
    messages = request.get("messages", [])
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        out(f"\n--- {role.upper()} ---")
        if len(content) > 2000:
            out(content[:2000])
            out(f"\n... (省略: 残り {len(content) - 2000} 文字) ...")
        else:
            out(content)
    out()

    # --- 直近の出来事セクションの確認（積み上がりの検証用）---
    user_content = next(
        (m.get("content", "") for m in messages if m.get("role") == "user"),
        "",
    )
    if "## 直近の出来事" in user_content:
        out("\n■ 直近の出来事セクション（観測・行動・結果の積み上げ）")
        out("-" * 40)
        start = user_content.find("## 直近の出来事")
        end = user_content.find("## ", start + 5)
        section = user_content[start:end] if end > 0 else user_content[start:]
        out(section.strip())
        out()

    # --- シミュレート出力 ---
    out("\n■ シミュレート出力（実際のLLMは呼ばない）")
    out("-" * 40)
    out(f"  ツール: {simulated_output.get('tool_name', '?')}")
    out(f"  行動要約: {simulated_output.get('action_summary', '?')}")
    out(f"  結果要約: {simulated_output.get('result_summary', '?')}")
    out()


def run_multiturn_demo(
    num_turns: int = 3,
    output_file=None,
) -> None:
    """マルチターンループをシミュレートし、各ターンのプロンプトを出力する。"""
    prompt_builder, repos = _setup_components()
    profile_repo = repos["profile_repo"]
    status_repo = repos["status_repo"]
    phys_repo = repos["phys_repo"]
    buffer = repos["buffer"]
    action_store = repos["action_store"]

    # プレイヤー配置
    profile_repo.save(_create_profile(1, "Alice"))
    exp_table = ExpTable(100, 1.5)
    status_repo.save(
        PlayerStatusAggregate(
            player_id=PlayerId(1),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold.create(0),
            hp=Hp.create(10, 10),
            mp=Mp.create(10, 10),
            stamina=Stamina.create(10, 10),
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
    )
    tiles = {
        Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
    }
    phys_repo.save(
        PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[
                WorldObject(
                    object_id=WorldObjectId.create(1),
                    coordinate=Coordinate(0, 0, 0),
                    object_type=ObjectTypeEnum.PLAYER,
                    component=ActorComponent(
                        direction=DirectionEnum.SOUTH,
                        player_id=PlayerId(1),
                    ),
                ),
            ],
        )
    )

    player_id = PlayerId(1)
    scenario = (DEFAULT_TURN_SCENARIO * ((num_turns // len(DEFAULT_TURN_SCENARIO)) + 1))[
        :num_turns
    ]

    for turn in range(1, num_turns + 1):
        obs_list, tool_name, action_summary, result_summary = scenario[turn - 1]

        # 1. 観測をバッファに追加（次の build で drain → sliding_window へ）
        for item in obs_list:
            if isinstance(item, tuple):
                obs_prose, obs_label = item
            else:
                obs_prose, obs_label = item, None
            _add_observation(
                buffer, player_id, obs_prose, game_time_label=obs_label
            )

        # 2. プロンプト構築（実際の LLM は呼ばない）
        request = prompt_builder.build(player_id)

        # 3. 出力
        _print_turn_result(
            turn,
            request,
            {
                "tool_name": tool_name,
                "action_summary": action_summary,
                "result_summary": result_summary,
            },
            output_file,
        )

        # 4. 行動結果をストアに追加（次ターンのプロンプトに反映）
        action_store.append(player_id, action_summary, result_summary)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM マルチターンループのプロンプト検証デモ（LLM API は呼ばない）"
    )
    parser.add_argument(
        "-n",
        "--num-turns",
        type=int,
        default=3,
        help="実行するターン数（デフォルト: 3）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="出力先ファイル。指定しない場合は標準出力",
    )
    args = parser.parse_args()

    if args.num_turns < 1:
        parser.error("ターン数は 1 以上で指定してください")

    output_file = open(args.output, "w", encoding="utf-8") if args.output else None
    try:
        def out(s: str) -> None:
            dst = output_file or sys.stdout
            print(s, file=dst)

        out("\n" + "#" * 80)
        out("# LLM マルチターン プロンプト検証デモ")
        out("# 観測→思考→行動→結果 のループをシミュレートし、各ターンのプロンプトを出力")
        out("# 実際の LLM API は呼ばず、出力はシミュレート値です")
        out("# 注: 「思考」は現在LLM内部で生成されストアされないため、プロンプトには含まれません")
        out("#" * 80)

        run_multiturn_demo(num_turns=args.num_turns, output_file=output_file)

        out("\n" + "=" * 80)
        out("検証完了。各ターンで「直近の出来事」に前ターンの観測・行動・結果が積み上がっていることを確認してください。")
        out("=" * 80 + "\n")
    finally:
        if output_file:
            output_file.close()
            print(f"出力を {args.output} に保存しました。", file=sys.stderr)


if __name__ == "__main__":
    main()
