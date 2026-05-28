"""TradeWiringConfig と GameRepositoriesConfig の構造保証。

Issue #227 後続 HIGH-4 Step 8c: wiring 引数を機能ごとに集約していくシリーズ。
本 Config はリポジトリ群 / 取引機能を 1 つにまとめるだけのコンテナで、
特別な制約 (assert) は持たない (個別のリポジトリは独立した aggregate を扱う)。
"""

from ai_rpg_world.application.llm.wiring.wiring_configs import (
    GameRepositoriesConfig,
    TradeWiringConfig,
)


class TestTradeWiringConfig:
    """TradeWiringConfig は 3 つの取引関連 field を持つ。"""

    def test_default_all_fields_none(self) -> None:
        cfg = TradeWiringConfig()
        assert cfg.command_service is None
        assert cfg.page_session is None
        assert cfg.page_query_service is None

    def test_construct_with_fields(self) -> None:
        a = object()
        b = object()
        c = object()
        cfg = TradeWiringConfig(
            command_service=a, page_session=b, page_query_service=c
        )
        assert cfg.command_service is a
        assert cfg.page_session is b
        assert cfg.page_query_service is c


class TestGameRepositoriesConfig:
    """GameRepositoriesConfig は ゲーム系リポジトリ 15 種を Optional で持つコンテナ。"""

    def test_default_all_fields_none(self) -> None:
        cfg = GameRepositoriesConfig()
        for field_name in (
            "item_repository",
            "item_spec_repository",
            "monster_repository",
            "monster_template_repository",
            "quest_repository",
            "shop_repository",
            "trade_repository",
            "guild_repository",
            "hit_box_repository",
            "skill_loadout_repository",
            "skill_deck_progress_repository",
            "skill_spec_repository",
            "sns_user_repository",
            "spot_repository",
            "spot_graph_repository",
        ):
            assert getattr(cfg, field_name) is None
