#!/usr/bin/env python3
"""
LLM エージェントに渡されるプロンプトの検証用デモスクリプト。

実際の LLM API を呼ばず、IPromptBuilder.build() の結果を様々なケースで出力し、
プロンプトの内容が妥当かどうかを検証できるようにする。

使い方:
    cd /path/to/ai_rpg_world
    source venv/bin/activate   # または pip install -e . でパッケージをインストール
    python scripts/demo_llm_prompt_inspection.py              # 全ケース実行
    python scripts/demo_llm_prompt_inspection.py --case 1,3,5 # 特定ケースのみ
    python scripts/demo_llm_prompt_inspection.py -o out.txt   # ファイルに出力
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
from ai_rpg_world.application.llm.services.predictive_memory_retriever import (
    DefaultPredictiveMemoryRetriever,
)
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
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
from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
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
    with_predictive_memory: bool = False,
) -> Tuple[DefaultPromptBuilder, Dict[str, Any]]:
    """PromptBuilder と各種リポジトリをセットアップする。"""
    ds = data_store or InMemoryDataStore()
    ds.clear_all()
    profile_repo = InMemoryPlayerProfileRepository(ds)
    status_repo = InMemoryPlayerStatusRepository(ds)
    phys_repo = InMemoryPhysicalMapRepository(ds)
    spot_repo = InMemorySpotRepository(ds)
    spot_repo.save(Spot(SpotId(1), "Default", ""))
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

    predictive_retriever = None
    if with_predictive_memory:
        episode_store = InMemoryEpisodeMemoryStore()
        long_term_store = InMemoryLongTermMemoryStore()
        long_term_store.add_fact(PlayerId(1), "洞窟の奥には宝箱がある。前回は開けた。")
        episode_entry = EpisodeMemoryEntry(
            id="ep-demo-test",
            context_summary="洞窟入口でモンスターと戦った",
            action_taken="world_attack",
            outcome_summary="モンスターを倒した。",
            entity_ids=("モンスター",),
            location_id="洞窟入口",
            timestamp=datetime.now(),
            importance="medium",
            surprise=False,
            recall_count=0,
        )
        episode_store.add(PlayerId(1), episode_entry)
        predictive_retriever = DefaultPredictiveMemoryRetriever(
            episode_store=episode_store,
            long_term_store=long_term_store,
        )

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
        predictive_memory_retriever=predictive_retriever,
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
    )
    buffer.append(player_id, entry)


def _print_prompt_result(
    case_name: str, result: Dict[str, Any], output_file=None
) -> None:
    """プロンプト結果を整形して出力する。output_file が指定されていればファイルに書き出す。"""
    def out(s: str = "") -> None:
        dst = output_file or sys.stdout
        print(s, file=dst)

    out("\n" + "=" * 80)
    out(f"【ケース】{case_name}")
    out("=" * 80)
    messages = result.get("messages", [])
    tools = result.get("tools", [])
    tool_names = [
        t["function"]["name"]
        for t in tools
        if t.get("type") == "function" and "function" in t
    ]
    out(f"\n■ ツール数: {len(tools)}")
    out(f"■ ツール名: {tool_names[:10]}{'...' if len(tool_names) > 10 else ''}\n")

    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        out(f"--- {role.upper()} MESSAGE ---")
        if len(content) > 1200:
            out(content[:1200])
            out(f"\n... (省略: 残り {len(content) - 1200} 文字) ...")
        else:
            out(content)
        out()


def run_case_1_unplaced(output_file=None):
    """ケース1: プレイヤー未配置（ゲーム参加前）"""
    prompt_builder, repos = _setup_components()
    profile_repo = repos["profile_repo"]
    profile_repo.save(_create_profile(1, "Alice"))

    result = prompt_builder.build(PlayerId(1))
    _print_prompt_result("1. プレイヤー未配置（ゲーム参加待機中）", result, output_file)


def run_case_2_placed_alone(output_file=None):
    """ケース2: 配置済み・単独（他プレイヤーなし）"""
    prompt_builder, repos = _setup_components()
    profile_repo = repos["profile_repo"]
    status_repo = repos["status_repo"]
    phys_repo = repos["phys_repo"]
    spot_repo = repos["spot_repo"]

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

    result = prompt_builder.build(PlayerId(1))
    _print_prompt_result("2. 配置済み・単独（他プレイヤーなし）", result, output_file)


def run_case_3_placed_with_other_players(output_file=None):
    """ケース3: 配置済み・他プレイヤーが視界内にいる"""
    prompt_builder, repos = _setup_components()
    profile_repo = repos["profile_repo"]
    status_repo = repos["status_repo"]
    phys_repo = repos["phys_repo"]

    profile_repo.save(_create_profile(1, "Alice"))
    profile_repo.save(_create_profile(2, "Bob"))
    exp_table = ExpTable(100, 1.5)
    for pid, coord in [(1, Coordinate(0, 0, 0)), (2, Coordinate(1, 0, 0))]:
        status_repo.save(
            PlayerStatusAggregate(
                player_id=PlayerId(pid),
                base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
                stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
                exp_table=exp_table,
                growth=Growth(1, 0, exp_table),
                gold=Gold.create(0),
                hp=Hp.create(10, 10),
                mp=Mp.create(10, 10),
                stamina=Stamina.create(10, 10),
                current_spot_id=SpotId(1),
                current_coordinate=coord,
            )
        )
    tiles = {
        Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
        Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.grass()),
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
                WorldObject(
                    object_id=WorldObjectId.create(2),
                    coordinate=Coordinate(1, 0, 0),
                    object_type=ObjectTypeEnum.PLAYER,
                    component=ActorComponent(
                        direction=DirectionEnum.SOUTH,
                        player_id=PlayerId(2),
                    ),
                ),
            ],
        )
    )

    result = prompt_builder.build(PlayerId(1))
    _print_prompt_result("3. 配置済み・他プレイヤー(Bob)が視界内にいる", result, output_file)


def run_case_4_with_observations_and_action_results(output_file=None):
    """ケース4: 観測＋行動結果あり（直近の出来事に情報あり）"""
    prompt_builder, repos = _setup_components()
    profile_repo = repos["profile_repo"]
    status_repo = repos["status_repo"]
    phys_repo = repos["phys_repo"]
    buffer = repos["buffer"]
    action_store = repos["action_store"]

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

    # 観測をバッファに追加
    _add_observation(
        buffer,
        PlayerId(1),
        "東方向に草原が広がっている。風が心地よい。",
        {"direction": "east", "terrain": "grass"},
    )
    _add_observation(
        buffer,
        PlayerId(1),
        "遠くに人影が見えた。",
        {"object_type": "player", "distance": 5},
    )
    # 行動結果を追加
    action_store.append(
        PlayerId(1),
        "world_set_destination({...}) を実行しました。",
        "移動を開始しました。現在スポット Default から隣のエリアへ向かっています。",
    )

    result = prompt_builder.build(PlayerId(1))
    _print_prompt_result("4. 観測＋行動結果あり（直近の出来事に情報あり）", result, output_file)


def run_case_5_with_predictive_memory(output_file=None):
    """ケース5: 関連する記憶あり（PredictiveMemoryRetriever 使用）"""
    prompt_builder, repos = _setup_components(with_predictive_memory=True)
    profile_repo = repos["profile_repo"]
    status_repo = repos["status_repo"]
    phys_repo = repos["phys_repo"]

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

    result = prompt_builder.build(PlayerId(1))
    _print_prompt_result("5. 関連する記憶あり（エピソード＋長期事実）", result, output_file)


def run_case_6_custom_action_instruction(output_file=None):
    """ケース6: カスタム action_instruction を指定"""
    prompt_builder, repos = _setup_components()
    profile_repo = repos["profile_repo"]
    profile_repo.save(_create_profile(1, "冒険者"))

    result = prompt_builder.build(
        PlayerId(1),
        action_instruction="今は会話を試みるか、もしくは待機してください。",
    )
    _print_prompt_result("6. カスタム action_instruction 指定", result, output_file)


CASE_RUNNERS = {
    1: run_case_1_unplaced,
    2: run_case_2_placed_alone,
    3: run_case_3_placed_with_other_players,
    4: run_case_4_with_observations_and_action_results,
    5: run_case_5_with_predictive_memory,
    6: run_case_6_custom_action_instruction,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM エージェントに渡されるプロンプトの検証デモ（LLM API は呼ばない）"
    )
    parser.add_argument(
        "--case", "-c",
        type=str,
        default="1,2,3,4,5,6",
        help="実行するケース番号（カンマ区切り）。例: 1,3,5",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="出力先ファイル。指定しない場合は標準出力",
    )
    args = parser.parse_args()

    case_nums: List[int] = []
    for part in args.case.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            if 1 <= n <= 6:
                case_nums.append(n)
            else:
                parser.error(f"ケース番号は 1-6 の範囲で指定してください: {n}")

    if not case_nums:
        parser.error("少なくとも1つのケースを指定してください")

    output_file = open(args.output, "w", encoding="utf-8") if args.output else None
    try:
        def out(s: str) -> None:
            dst = output_file or sys.stdout
            print(s, file=dst)

        out("\n" + "#" * 80)
        out("# LLM エージェント プロンプト検証デモ")
        out("# 実際の LLM API は呼ばず、build() の結果のみ出力します")
        out("#" * 80)

        for n in sorted(set(case_nums)):
            CASE_RUNNERS[n](output_file)

        out("\n" + "=" * 80)
        out("すべてのケースの検証が完了しました。")
        out("=" * 80 + "\n")
    finally:
        if output_file:
            output_file.close()
            print(f"出力を {args.output} に保存しました。", file=sys.stderr)


if __name__ == "__main__":
    main()
