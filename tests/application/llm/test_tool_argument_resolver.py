"""DefaultToolArgumentResolver のテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ActiveHarvestToolRuntimeTargetDto,
    AttentionLevelToolRuntimeTargetDto,
    AwakenedActionToolRuntimeTargetDto,
    ChestItemToolRuntimeTargetDto,
    ChestToolRuntimeTargetDto,
    ConversationChoiceToolRuntimeTargetDto,
    DestinationToolRuntimeTargetDto,
    GuildToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ResourceToolRuntimeTargetDto,
    ShopListingToolRuntimeTargetDto,
    ShopToolRuntimeTargetDto,
    SkillEquipCandidateToolRuntimeTargetDto,
    SkillEquipSlotToolRuntimeTargetDto,
    SkillProposalToolRuntimeTargetDto,
    SkillToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.guild_shop_trade_resolver import (
    GuildShopTradeArgumentResolver,
)
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_QUEST_ISSUE,
    TOOL_NAME_SHOP_LIST_ITEM,
    TOOL_NAME_SPEECH,
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_DECLINE,
    TOOL_NAME_TRADE_OFFER,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "S1": DestinationToolRuntimeTargetDto(
                label="S1",
                kind="destination",
                display_name="港町",
                spot_id=2,
                destination_type="spot",
            ),
            "L1": DestinationToolRuntimeTargetDto(
                label="L1",
                kind="destination",
                display_name="ギルドエリア",
                spot_id=1,
                tile_location_area_id=10,
                destination_type="location",
            ),
            "D1": DestinationToolRuntimeTargetDto(
                label="D1",
                kind="destination",
                display_name="老人",
                spot_id=1,
                world_object_id=200,
                target_x=0,
                target_y=1,
                target_z=0,
                destination_type="object",
            ),
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="player",
                display_name="Bob",
                player_id=2,
                world_object_id=100,
            ),
            "N1": NpcToolRuntimeTargetDto(
                label="N1",
                kind="npc",
                display_name="老人",
                world_object_id=200,
            ),
            "O2": ChestToolRuntimeTargetDto(
                label="O2",
                kind="chest",
                display_name="宝箱",
                world_object_id=210,
            ),
            "O1": ResourceToolRuntimeTargetDto(
                label="O1",
                kind="resource",
                display_name="薬草",
                world_object_id=300,
            ),
            "H1": ActiveHarvestToolRuntimeTargetDto(
                label="H1",
                kind="active_harvest",
                display_name="薬草",
                world_object_id=300,
            ),
            "I1": InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="木箱",
                item_instance_id=400,
                inventory_slot_id=2,
                is_placeable=True,
                available_interactions=("place_object",),
            ),
            "C1": ChestItemToolRuntimeTargetDto(
                label="C1",
                kind="chest_item",
                display_name="ポーション",
                item_instance_id=500,
                chest_world_object_id=210,
            ),
            "R1": ConversationChoiceToolRuntimeTargetDto(
                label="R1",
                kind="conversation_choice",
                display_name="はい",
                world_object_id=200,
                conversation_choice_index=0,
            ),
            "K1": SkillToolRuntimeTargetDto(
                label="K1",
                kind="skill",
                display_name="火球",
                skill_loadout_id=10,
                skill_slot_index=1,
            ),
            "EK1": SkillEquipCandidateToolRuntimeTargetDto(
                label="EK1",
                kind="skill_equip_candidate",
                display_name="火球",
                skill_loadout_id=10,
                skill_id=1001,
            ),
            "ES1": SkillEquipSlotToolRuntimeTargetDto(
                label="ES1",
                kind="skill_equip_slot",
                display_name="通常スロット 1",
                skill_loadout_id=10,
                deck_tier=DeckTier.NORMAL,
                skill_slot_index=0,
            ),
            "SP1": SkillProposalToolRuntimeTargetDto(
                label="SP1",
                kind="skill_proposal",
                display_name="新しい攻撃手段",
                progress_id=20,
                proposal_id=2,
                target_slot_index=0,
                target_slot_display_name="通常スロット 1",
            ),
            "AW1": AwakenedActionToolRuntimeTargetDto(
                label="AW1",
                kind="awakened_action",
                display_name="覚醒モードを発動",
                skill_loadout_id=10,
            ),
            "A1": AttentionLevelToolRuntimeTargetDto(
                label="A1",
                kind="attention_level",
                display_name="フル",
                attention_level_value="FULL",
            ),
        }
    )


class TestDefaultToolArgumentResolver:
    def test_resolve_whisper_target_label(self):
        """Issue #264 後続: 統合された speech tool で channel=whisper を解決する。"""
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_SPEECH,
            {"channel": "whisper", "target_label": "P1", "content": "こんにちは"},
            _make_context(),
        )

        assert result["target_player_id"] == 2
        assert result["content"] == "こんにちは"
        assert result["channel"] == SpeechChannel.WHISPER

    def test_resolve_say_sets_say_channel(self):
        """Issue #264 後続: channel=say を解決すると SpeechChannel.SAY が入る。"""
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_SPEECH,
            {"channel": "say", "content": "やあ"},
            _make_context(),
        )

        assert result["content"] == "やあ"
        assert result["channel"] == SpeechChannel.SAY

    def test_resolve_shout_sets_shout_channel(self):
        """Issue #264 後続: channel=shout を解決すると SpeechChannel.SHOUT が入る (新規)。"""
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_SPEECH,
            {"channel": "shout", "content": "聞こえるか！"},
            _make_context(),
        )

        assert result["content"] == "聞こえるか！"
        assert result["channel"] == SpeechChannel.SHOUT

    def test_resolve_whisper_non_player_label_raises(self):
        """channel=whisper で target_label が non-player なら INVALID_TARGET_KIND。"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_SPEECH,
                {"channel": "whisper", "target_label": "N1", "content": "こんにちは"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"


class TestDefaultToolArgumentResolverInputValidation:
    """resolve() の入力バリデーション（TypeError）"""

    def test_resolve_tool_name_not_str_raises_type_error(self):
        resolver = DefaultToolArgumentResolver()
        with pytest.raises(TypeError, match="tool_name must be str"):
            resolver.resolve(123, {}, _make_context())  # type: ignore[arg-type]

    def test_resolve_arguments_not_dict_raises_type_error(self):
        resolver = DefaultToolArgumentResolver()
        with pytest.raises(TypeError, match="arguments must be dict or None"):
            resolver.resolve(
                TOOL_NAME_SPEECH,
                "invalid",  # type: ignore[arg-type]
                _make_context(),
            )

    def test_resolve_runtime_context_invalid_raises_type_error(self):
        resolver = DefaultToolArgumentResolver()
        with pytest.raises(TypeError, match="runtime_context must be ToolRuntimeContextDto"):
            resolver.resolve(
                TOOL_NAME_SPEECH,
                {},
                None,  # type: ignore[arg-type]
            )


def _make_shop_guild_trade_context() -> ToolRuntimeContextDto:
    """ショップ・ギルド・取引テスト用の拡張コンテキスト"""
    base = _make_context()
    extra = {
        "G1": GuildToolRuntimeTargetDto(
            label="G1",
            kind="guild",
            display_name="冒険者ギルド",
            guild_id=1,
        ),
        "SH1": ShopToolRuntimeTargetDto(
            label="SH1",
            kind="shop",
            display_name="港町ショップ",
            shop_id=10,
        ),
        "SL1": ShopListingToolRuntimeTargetDto(
            label="SL1",
            kind="shop_listing",
            display_name="木箱 100G",
            shop_id=10,
            listing_id=5,
        ),
    }
    return ToolRuntimeContextDto(targets={**base.targets, **extra})


class TestDefaultToolArgumentResolverSafeInt:
    """_safe_int 経由の数値変換（不正値で ToolArgumentResolutionException）"""

    def test_resolve_shop_list_item_price_invalid_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_SHOP_LIST_ITEM,
                {
                    "shop_label": "SH1",
                    "inventory_item_label": "I1",
                    "price_per_unit": "not_a_number",
                },
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "整数" in str(exc_info.value)

    def test_resolve_guild_label_amount_invalid_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_GUILD_DEPOSIT_BANK,
                {"guild_label": "G1", "amount": "invalid"},
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "整数" in str(exc_info.value)


class TestTheLegacyResolverNoLongerClaimsTheTradeNames:
    """旧マーケットボードの resolver は trade_offer 系の名前を解決しない。

    これらの名前は、同席したエージェント同士の取引 (spot_graph 側) が引き
    継いだ。resolver chain は「None を返したら次へ」の fall-through なので、
    旧実装に担当を残すと、新経路が何かの拍子に None を返した瞬間に
    **同名・別引数の旧実装へ黙って落ちる**。名前の併存そのものを禁じる。

    skip ではなく負のテストにしてあるのは、担当が戻されたことを検出したい
    から。skip は腐るだけで、乗っ取り返しを止められない。
    """

    def test_the_legacy_resolver_declines_trade_offer(self):
        """旧 resolver は trade_offer を解決せず、次の resolver へ譲る。"""
        assert (
            GuildShopTradeArgumentResolver().resolve_args(
                TOOL_NAME_TRADE_OFFER,
                {"inventory_item_label": "I1", "requested_gold": 5},
                _make_shop_guild_trade_context(),
            )
            is None
        )

    @pytest.mark.parametrize("tool_name", [TOOL_NAME_TRADE_ACCEPT, TOOL_NAME_TRADE_DECLINE])
    def test_the_legacy_resolver_declines_the_answer_tools(self, tool_name: str):
        """旧 resolver は trade_accept / trade_decline を解決せず、次へ譲る。"""
        assert (
            GuildShopTradeArgumentResolver().resolve_args(
                tool_name,
                {"trade_ref": "r_trade_x"},
                _make_context(),
            )
            is None
        )

    def test_trade_cancel_is_still_owned_by_the_legacy_resolver(self):
        """衝突していない trade_cancel は旧 resolver が持ったままになる。

        「取引まわりを全部落とした」のではなく「同じ名前の担当だけ外した」
        ことを固定する。
        """
        assert GuildShopTradeArgumentResolver().resolve_args(
            TOOL_NAME_TRADE_CANCEL,
            {"trade_ref": "  r_trade_x  "},
            _make_context(),
        ) == {"trade_ref": "r_trade_x"}


class TestToolArgumentResolverGuildCreate:
    """guild_create の resolve テスト"""

    def test_resolve_guild_create_success(self):
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(
            targets={},
            current_spot_id=1,
            current_area_ids=(10, 20),
        )
        result = resolver.resolve(
            TOOL_NAME_GUILD_CREATE,
            {"name": "冒険者ギルド", "description": "一緒に冒険"},
            ctx,
        )
        assert result["spot_id"] == 1
        assert result["location_area_id"] == 10
        assert result["name"] == "冒険者ギルド"
        assert result["description"] == "一緒に冒険"

    def test_resolve_guild_create_missing_area_ids_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={}, current_spot_id=1, current_area_ids=None)
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_GUILD_CREATE,
                {"name": "テスト"},
                ctx,
            )
        assert exc_info.value.error_code == "MISSING_CURRENT_AREA"


class TestToolArgumentResolverGuildDisband:
    """guild_disband の resolve テスト"""

    def test_resolve_guild_disband_success(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        result = resolver.resolve(TOOL_NAME_GUILD_DISBAND, {"guild_label": "G1"}, ctx)
        assert result["guild_id"] == 1


class TestToolArgumentResolverQuestIssue:
    """quest_issue の resolve テスト"""

    def test_resolve_quest_issue_success_public(self):
        """公開クエスト（guild_label なし）の解決"""
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "kill_monster", "target_id": 101, "required_count": 2},
                ],
                "reward_gold": 50,
            },
            ctx,
        )
        assert result["objectives"] == [("kill_monster", 101, 2)]
        assert result["reward_gold"] == 50
        assert result["reward_exp"] == 0
        assert result["reward_items"] is None
        assert result["guild_id"] is None

    def test_resolve_quest_issue_with_guild_label(self):
        """ギルド掲示クエストの解決"""
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "talk_to_npc", "target_id": 5, "required_count": 1},
                ],
                "guild_label": "G1",
            },
            ctx,
        )
        assert result["objectives"] == [("talk_to_npc", 5, 1)]
        assert result["guild_id"] == 1

    def test_resolve_quest_issue_empty_objectives_raises(self):
        """objectives が空のとき INVALID_OBJECTIVES"""
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {"objectives": []},
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_OBJECTIVES"

    def test_resolve_quest_issue_with_reward_items(self):
        """報酬アイテム付きの解決"""
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "obtain_item", "target_id": 201, "required_count": 1},
                ],
                "reward_items": [{"item_spec_id": 301, "quantity": 2}],
            },
            ctx,
        )
        assert result["objectives"] == [("obtain_item", 201, 1)]
        assert result["reward_items"] == [(301, 2)]


def _make_resolver_with_repos():
    """target_name 解決用のリポジトリ付き Resolver を構築"""
    from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
    from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
    from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
    from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
    from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
    from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
    from ai_rpg_world.domain.player.enum.player_enum import Race
    from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
    from ai_rpg_world.domain.player.value_object.player_id import PlayerId
    from ai_rpg_world.domain.player.value_object.player_name import PlayerName
    from ai_rpg_world.domain.world.entity.spot import Spot
    from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId
    from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
    from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository
    from ai_rpg_world.infrastructure.repository.in_memory_monster_template_repository import (
        InMemoryMonsterTemplateRepository,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
        InMemoryPlayerProfileRepository,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository

    monster_repo = InMemoryMonsterTemplateRepository()
    monster_repo.save(
        MonsterTemplate(
            template_id=MonsterTemplateId(10),
            name="ゴブリン",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="ゴブリン",
            skill_ids=[],
        )
    )

    data_store = InMemoryDataStore()
    data_store.clear_all()
    spot_repo = InMemorySpotRepository(data_store=data_store)
    spot_repo.save(Spot(SpotId(20), "北の森", "暗い森", SpotCategoryEnum.OTHER))

    item_repo = InMemoryItemSpecRepository()  # 鉄の剣 (id=1) がサンプルで入っている

    profile_repo = InMemoryPlayerProfileRepository(data_store=data_store)
    profile_repo.save(
        PlayerProfileAggregate.create(
            player_id=PlayerId(30),
            name=PlayerName("Alice"),
        )
    )

    return DefaultToolArgumentResolver(
        monster_template_repository=monster_repo,
        spot_repository=spot_repo,
        item_spec_repository=item_repo,
        player_profile_repository=profile_repo,
    )


class TestToolArgumentResolverQuestIssueTargetName:
    """quest_issue の target_name 解決テスト"""

    def test_resolve_quest_issue_target_name_kill_monster(self):
        """target_name で kill_monster（モンスター名→template_id）"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "kill_monster", "target_name": "ゴブリン", "required_count": 3},
                ],
                "reward_gold": 0,
            },
            ctx,
        )
        assert result["objectives"] == [("kill_monster", 10, 3)]

    def test_resolve_quest_issue_target_name_obtain_item(self):
        """target_name で obtain_item（アイテム名→item_spec_id）"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "obtain_item", "target_name": "鉄の剣", "required_count": 1},
                ],
                "reward_gold": 0,
            },
            ctx,
        )
        assert result["objectives"] == [("obtain_item", 1, 1)]

    def test_resolve_quest_issue_target_name_reach_spot(self):
        """target_name で reach_spot（スポット名→spot_id）"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "reach_spot", "target_name": "北の森", "required_count": 1},
                ],
                "reward_gold": 0,
            },
            ctx,
        )
        assert result["objectives"] == [("reach_spot", 20, 1)]

    def test_resolve_quest_issue_target_name_kill_player(self):
        """target_name で kill_player（プレイヤー名→player_id）"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "kill_player", "target_name": "Alice", "required_count": 1},
                ],
                "reward_gold": 0,
            },
            ctx,
        )
        assert result["objectives"] == [("kill_player", 30, 1)]

    def test_resolve_quest_issue_target_name_with_guild_label(self):
        """target_name と guild_label の組み合わせ"""
        resolver = _make_resolver_with_repos()
        ctx = _make_shop_guild_trade_context()
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "kill_monster", "target_name": "ゴブリン", "required_count": 2},
                ],
                "guild_label": "G1",
            },
            ctx,
        )
        assert result["objectives"] == [("kill_monster", 10, 2)]
        assert result["guild_id"] == 1

    def test_resolve_quest_issue_target_name_monster_not_found(self):
        """target_name が存在しないモンスター名 → MONSTER_TEMPLATE_NOT_FOUND"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {
                    "objectives": [
                        {"objective_type": "kill_monster", "target_name": "ドラゴン", "required_count": 1},
                    ],
                    "reward_gold": 0,
                },
                ctx,
            )
        assert exc_info.value.error_code == "MONSTER_TEMPLATE_NOT_FOUND"

    def test_resolve_quest_issue_target_name_spot_not_found(self):
        """target_name が存在しないスポット名 → SPOT_NOT_FOUND"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {
                    "objectives": [
                        {"objective_type": "reach_spot", "target_name": "存在しない場所", "required_count": 1},
                    ],
                    "reward_gold": 0,
                },
                ctx,
            )
        assert exc_info.value.error_code == "SPOT_NOT_FOUND"

    def test_resolve_quest_issue_target_name_item_not_found(self):
        """target_name が存在しないアイテム名 → ITEM_SPEC_NOT_FOUND"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {
                    "objectives": [
                        {"objective_type": "obtain_item", "target_name": "存在しないアイテム", "required_count": 1},
                    ],
                    "reward_gold": 0,
                },
                ctx,
            )
        assert exc_info.value.error_code == "ITEM_SPEC_NOT_FOUND"

    def test_resolve_quest_issue_target_name_player_not_found(self):
        """target_name が存在しないプレイヤー名 → PLAYER_PROFILE_NOT_FOUND"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {
                    "objectives": [
                        {"objective_type": "kill_player", "target_name": "存在しない人", "required_count": 1},
                    ],
                    "reward_gold": 0,
                },
                ctx,
            )
        assert exc_info.value.error_code == "PLAYER_PROFILE_NOT_FOUND"

    def test_resolve_quest_issue_target_name_resolver_not_configured(self):
        """リポジトリ None のときに target_name を指定 → RESOLVER_NOT_CONFIGURED"""
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {
                    "objectives": [
                        {"objective_type": "kill_monster", "target_name": "ゴブリン", "required_count": 1},
                    ],
                    "reward_gold": 0,
                },
                ctx,
            )
        assert exc_info.value.error_code == "RESOLVER_NOT_CONFIGURED"

    def test_resolve_quest_issue_target_name_and_target_id_target_name_priority(self):
        """target_name と target_id の両方がある場合、target_name を優先"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {
                        "objective_type": "kill_monster",
                        "target_name": "ゴブリン",
                        "target_id": 999,
                        "required_count": 1,
                    },
                ],
                "reward_gold": 0,
            },
            ctx,
        )
        assert result["objectives"] == [("kill_monster", 10, 1)]

    def test_resolve_quest_issue_target_name_and_target_id_neither_raises(self):
        """target_name も target_id もない → INVALID_OBJECTIVES"""
        resolver = _make_resolver_with_repos()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {
                    "objectives": [
                        {"objective_type": "kill_monster", "required_count": 1},
                    ],
                    "reward_gold": 0,
                },
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_OBJECTIVES"
