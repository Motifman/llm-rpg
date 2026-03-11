"""DefaultLlmUiContextBuilder のテスト。"""

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ResourceToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.ui_context_builder import (
    DefaultLlmUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import (
    ActiveConversationDto,
    AvailableLocationAreaDto,
    AvailableMoveDto,
    AttentionLevelOptionDto,
    ChestItemDto,
    ConversationChoiceDto,
    GuildMemberSummaryDto,
    GuildMembershipSummaryDto,
    InventoryItemDto,
    NearbyShopSummaryDto,
    PlayerCurrentStateDto,
    UsableSkillDto,
    VisibleObjectDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_state() -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="Alice",
        current_spot_id=1,
        current_spot_name="広場",
        current_spot_description="人が集まる広場",
        x=0,
        y=0,
        z=0,
        area_id=None,
        area_name=None,
        current_player_count=2,
        current_player_ids={1, 2},
        connected_spot_ids={2},
        connected_spot_names={"港町"},
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type="grass",
        visible_objects=[
            VisibleObjectDto(
                object_id=100,
                object_type="PLAYER",
                x=1,
                y=0,
                z=0,
                distance=1,
                display_name="Bob",
                object_kind="player",
                direction_from_player="東",
                player_id_value=2,
                is_self=False,
                is_notable=True,
                notable_reason="player",
            ),
            VisibleObjectDto(
                object_id=1,
                object_type="PLAYER",
                x=0,
                y=0,
                z=0,
                distance=0,
                display_name="Alice",
                object_kind="player",
                direction_from_player="ここ",
                player_id_value=1,
                is_self=True,
            ),
            VisibleObjectDto(
                object_id=200,
                object_type="NPC",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                direction_from_player="南",
                is_interactable=True,
                interaction_type="talk",
                available_interactions=["interact"],
                can_interact=True,
                is_notable=True,
                notable_reason="actionable",
            ),
            VisibleObjectDto(
                object_id=300,
                object_type="RESOURCE",
                x=-1,
                y=0,
                z=0,
                distance=1,
                display_name="薬草",
                object_kind="resource",
                direction_from_player="西",
                available_interactions=["harvest"],
                can_harvest=True,
                is_notable=True,
                notable_reason="actionable",
            ),
        ],
        view_distance=5,
        available_moves=[
            AvailableMoveDto(
                spot_id=2,
                spot_name="港町",
                road_id=1,
                road_description="街道",
                conditions_met=True,
                failed_conditions=[],
            )
        ],
        total_available_moves=1,
        attention_level=AttentionLevel.FULL,
        inventory_items=[
            InventoryItemDto(0, 401, "木箱", 1, is_placeable=True),
        ],
        chest_items=[
            ChestItemDto(200, "宝箱", 501, "ポーション", 1),
        ],
        active_conversation=ActiveConversationDto(
            npc_world_object_id=200,
            npc_display_name="老人",
            node_text="どうする？",
            choices=[ConversationChoiceDto(display_text="はい", choice_index=0)],
            is_terminal=False,
        ),
        usable_skills=[
            UsableSkillDto(10, 1, 1001, "火球", mp_cost=5),
        ],
        attention_level_options=[
            AttentionLevelOptionDto("FULL", "フル", "すべての観測を受け取ります。"),
        ],
        can_destroy_placeable=True,
        actionable_objects=[
            VisibleObjectDto(
                object_id=200,
                object_type="NPC",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                direction_from_player="南",
                is_interactable=True,
                interaction_type="talk",
                available_interactions=["interact"],
                can_interact=True,
                is_notable=True,
                notable_reason="actionable",
            ),
            VisibleObjectDto(
                object_id=300,
                object_type="RESOURCE",
                x=-1,
                y=0,
                z=0,
                distance=1,
                display_name="薬草",
                object_kind="resource",
                direction_from_player="西",
                available_interactions=["harvest"],
                can_harvest=True,
                is_notable=True,
                notable_reason="actionable",
            ),
        ],
        notable_objects=[
            VisibleObjectDto(
                object_id=100,
                object_type="PLAYER",
                x=1,
                y=0,
                z=0,
                distance=1,
                display_name="Bob",
                object_kind="player",
                direction_from_player="東",
                player_id_value=2,
                is_self=False,
                is_notable=True,
                notable_reason="player",
            ),
            VisibleObjectDto(
                object_id=200,
                object_type="NPC",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                direction_from_player="南",
                is_interactable=True,
                interaction_type="talk",
                available_interactions=["interact"],
                can_interact=True,
                is_notable=True,
                notable_reason="actionable",
            ),
            VisibleObjectDto(
                object_id=300,
                object_type="RESOURCE",
                x=-1,
                y=0,
                z=0,
                distance=1,
                display_name="薬草",
                object_kind="resource",
                direction_from_player="西",
                available_interactions=["harvest"],
                can_harvest=True,
                is_notable=True,
                notable_reason="actionable",
            ),
        ],
    )


class TestDefaultLlmUiContextBuilder:
    def test_build_adds_visible_target_labels_and_runtime_context(self):
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()

        result = builder.build("現在地: 広場", state)

        assert "視界内の対象ラベル:" in result.current_state_text
        assert "注目対象ラベル:" in result.current_state_text
        assert "今すぐ行動可能な対象ラベル:" in result.current_state_text
        assert "P1: Bob" in result.current_state_text
        assert "N1: 老人" in result.current_state_text
        assert "相互作用可能" in result.current_state_text
        assert "採集可能" in result.current_state_text
        assert "理由:" in result.current_state_text
        assert isinstance(result.tool_runtime_context, ToolRuntimeContextDto)
        assert isinstance(result.tool_runtime_context.targets["P1"], PlayerToolRuntimeTargetDto)
        assert isinstance(result.tool_runtime_context.targets["N1"], NpcToolRuntimeTargetDto)
        assert isinstance(result.tool_runtime_context.targets["O1"], ResourceToolRuntimeTargetDto)
        assert result.tool_runtime_context.targets["P1"].player_id == 2
        assert result.tool_runtime_context.targets["P1"].relative_dx == 1
        assert result.tool_runtime_context.targets["P1"].relative_dy == 0
        assert result.tool_runtime_context.targets["N1"].world_object_id == 200
        assert result.tool_runtime_context.targets["N1"].interaction_type == "talk"
        assert result.tool_runtime_context.targets["O1"].available_interactions == ("harvest",)
        assert "インベントリアイテム:" in result.current_state_text
        assert "I1: 木箱" in result.current_state_text
        assert "開いているチェストの中身:" in result.current_state_text
        assert "C1: ポーション" in result.current_state_text
        assert "会話中:" in result.current_state_text
        assert "R1: はい" in result.current_state_text
        assert "使用可能スキル:" in result.current_state_text
        assert "K1: 火球" in result.current_state_text
        assert "注意レベル変更:" in result.current_state_text
        assert "A1: フル" in result.current_state_text
        assert result.tool_runtime_context.current_x == 0
        assert result.tool_runtime_context.targets["I1"].inventory_slot_id == 0
        assert isinstance(result.tool_runtime_context.targets["I1"], InventoryToolRuntimeTargetDto)
        assert result.tool_runtime_context.targets["I1"].is_placeable is True
        assert result.tool_runtime_context.targets["C1"].chest_world_object_id == 200
        assert result.tool_runtime_context.targets["R1"].conversation_choice_index == 0
        assert result.tool_runtime_context.targets["K1"].skill_slot_index == 1
        assert result.tool_runtime_context.targets["A1"].attention_level_value == "FULL"

    def test_build_adds_move_labels(self):
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()

        result = builder.build("現在地: 広場", state)

        assert "移動先ラベル:" in result.current_state_text
        assert "S1: 港町" in result.current_state_text
        assert result.tool_runtime_context.targets["S1"].spot_id == 2
        assert result.tool_runtime_context.targets["S1"].destination_type == "spot"

    def test_build_adds_location_labels_when_available_location_areas_present(self):
        """available_location_areas があるとき L1, L2 が移動先ラベルに含まれる"""
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()
        state.available_location_areas = [
            AvailableLocationAreaDto(location_area_id=10, name="ギルドエリア"),
            AvailableLocationAreaDto(location_area_id=20, name="市場"),
        ]

        result = builder.build("現在地: 広場", state)

        assert "移動先ラベル:" in result.current_state_text
        assert "L1: ギルドエリア（同一スポット内ロケーション）" in result.current_state_text
        assert "L2: 市場（同一スポット内ロケーション）" in result.current_state_text
        assert "S1: 港町" in result.current_state_text
        assert "L1" in result.tool_runtime_context.targets
        assert "L2" in result.tool_runtime_context.targets
        target_l1 = result.tool_runtime_context.targets["L1"]
        assert target_l1.destination_type == "location"
        assert target_l1.location_area_id == 10
        assert target_l1.spot_id == 1
        assert target_l1.display_name == "ギルドエリア"

    def test_build_adds_only_location_labels_when_no_available_moves(self):
        """available_moves がなく available_location_areas のみあるときも移動先ラベルを出す"""
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()
        state.available_moves = []
        state.total_available_moves = 0
        state.available_location_areas = [
            AvailableLocationAreaDto(location_area_id=10, name="広場中央"),
        ]

        result = builder.build("現在地: 広場", state)

        assert "移動先ラベル:" in result.current_state_text
        assert "L1: 広場中央（同一スポット内ロケーション）" in result.current_state_text
        assert "L1" in result.tool_runtime_context.targets

    def test_build_adds_object_destination_labels_when_actionable_objects_present(self):
        """actionable_objects があるとき D1, D2 が移動先ラベルに含まれる（自分を除く）"""
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()
        state.actionable_objects = [
            VisibleObjectDto(
                object_id=200,
                object_type="NPC",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                available_interactions=["interact"],
            ),
            VisibleObjectDto(
                object_id=300,
                object_type="RESOURCE",
                x=-1,
                y=0,
                z=0,
                distance=1,
                display_name="薬草",
                object_kind="resource",
                available_interactions=["harvest"],
            ),
        ]

        result = builder.build("現在地: 広場", state)

        assert "移動先ラベル:" in result.current_state_text
        assert "D1: 老人（オブジェクトへ向かう）" in result.current_state_text
        assert "D2: 薬草（オブジェクトへ向かう）" in result.current_state_text
        target_d1 = result.tool_runtime_context.targets["D1"]
        assert target_d1.destination_type == "object"
        assert target_d1.world_object_id == 200
        assert target_d1.spot_id == 1
        assert target_d1.display_name == "老人"

    def test_build_object_labels_exclude_self(self):
        """actionable_objects に is_self なオブジェクトが含まれても D ラベルに含めない"""
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()
        state.actionable_objects = [
            VisibleObjectDto(
                object_id=1,
                object_type="PLAYER",
                x=0,
                y=0,
                z=0,
                distance=0,
                display_name="Alice",
                object_kind="player",
                is_self=True,
            ),
        ]

        result = builder.build("現在地: 広場", state)

        assert "D1" not in result.tool_runtime_context.targets

    def test_build_with_none_state_returns_empty_runtime_context(self):
        builder = DefaultLlmUiContextBuilder()

        result = builder.build("現在地: 未配置", None)

        assert result.current_state_text == "現在地: 未配置"
        assert result.tool_runtime_context.targets == {}

    def test_build_includes_guild_description_when_present(self):
        """ギルドに description がある場合、所属ギルド行に含まれる"""
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()
        state.guild_memberships = [
            GuildMembershipSummaryDto(
                guild_id=1,
                guild_name="冒険者ギルド",
                role="リーダー",
                description="一緒に冒険しましょう",
            ),
        ]

        result = builder.build("現在地: 広場", state)

        assert "所属ギルド:" in result.current_state_text
        assert "G1: 冒険者ギルド" in result.current_state_text
        assert "一緒に冒険しましょう" in result.current_state_text

    def test_build_includes_shop_description_when_present(self):
        """ショップに description がある場合、近隣ショップ行に含まれる"""
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()
        state.nearby_shops = [
            NearbyShopSummaryDto(
                shop_id=1,
                shop_name="ポーション屋",
                listing_count=0,
                listings=[],
                description="様々な薬を扱う店です",
            ),
        ]

        result = builder.build("現在地: 広場", state)

        assert "近隣ショップ:" in result.current_state_text
        assert "SH1: ポーション屋" in result.current_state_text
        assert "様々な薬を扱う店です" in result.current_state_text

    def test_build_includes_guild_member_labels_when_members_present(self):
        """ギルドに members がある場合、GM1, GM2 等のラベルが表示される"""
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()
        state.guild_memberships = [
            GuildMembershipSummaryDto(
                guild_id=1,
                guild_name="冒険者ギルド",
                role="leader",
                description="一緒に冒険しましょう",
                members=[
                    GuildMemberSummaryDto(player_id=1, player_name="Alice", role="leader"),
                    GuildMemberSummaryDto(player_id=2, player_name="Bob", role="member"),
                ],
            ),
        ]

        result = builder.build("現在地: 広場", state)

        assert "所属ギルド:" in result.current_state_text
        assert "G1: 冒険者ギルド" in result.current_state_text
        assert "GM1: Alice（leader）" in result.current_state_text
        assert "GM2: Bob（member）" in result.current_state_text
        assert "GM1" in result.tool_runtime_context.targets
        assert "GM2" in result.tool_runtime_context.targets
        gm1 = result.tool_runtime_context.targets["GM1"]
        assert gm1.player_id == 1
        assert gm1.display_name == "Alice"
