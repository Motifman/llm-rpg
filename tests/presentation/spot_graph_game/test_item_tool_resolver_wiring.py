"""#356 実験 #25 OFF で発覚した item tool resolver gap の regression 防止。

実験 trace 上で 164 件の INVALID_ARGUMENT が出ていた:
- use_item: 106 件全失敗 (LLM が `item_label: "I1"` を送るが executor は `item_spec_id` を読む)
- drop_item: 25 件失敗 (resolver dispatch にはあるが experiment wiring が呼ばない)
- give_item: 18 件失敗 (同上)
- pickup_item: 15 件失敗 (同上)

原因: `_WorldLlmWiring._wire_missing_spot_graph_tools` が executor を
`_adapt_executor_handler` で直接ラップしていて、引数 resolver
(SpotGraphArgumentResolver) を経由していなかった。

本テストは:
1. resolver の `_resolve_use_item` が item_label → item_spec_id を返す
2. `_adapt_executor_handler_with_resolver` が resolver を呼んで executor に
   解決済み args を渡すこと
3. resolver 例外が LlmCommandResultDto に変換され、success=False で
   INVALID_TARGET_LABEL を返すこと
を保証する。
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    LlmCommandResultDto,
    MonsterToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _WorldLlmWiring,
)


def _inventory_target(
    label: str = "I1",
    item_spec_id: int = 42,
    slot_id: int = 7,
    instance_id: int = 100,
    display_name: str = "椰子の実",
) -> InventoryToolRuntimeTargetDto:
    return InventoryToolRuntimeTargetDto(
        label=label,
        kind="inventory_item",
        display_name=display_name,
        # legacy: use_item は item_instance_id フィールドに item_spec_id を入れる慣習
        item_instance_id=item_spec_id,
        real_item_instance_id=instance_id,
        inventory_slot_id=slot_id,
    )


def _runtime_context(targets: Dict[str, Any]) -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(targets=targets)


class TestResolveUseItem:
    """`SpotGraphArgumentResolver._resolve_use_item` の基本動作。"""

    def test_item_label_item_spec_id(self) -> None:
        """itemlabel を itemspecid に変換。"""
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({"I1": _inventory_target(item_spec_id=42)})
        out = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            {"item_label": "I1", "inner_thought": "食べたい"},
            ctx,
        )
        assert out is not None
        assert out["item_spec_id"] == 42
        assert out["inner_thought"] == "食べたい"

    def test_item_label_empty_string_invalid_target_label_raises_exception(self) -> None:
        """itemlabel が空文字なら INVALIDTARGETLABEL 例外。"""
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({})
        with pytest.raises(ToolArgumentResolutionException) as ei:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_USE_ITEM, {"item_label": ""}, ctx,
            )
        assert ei.value.error_code == "INVALID_TARGET_LABEL"

    def test_missing_label_raises_exception_2(self) -> None:
        """存在しない label は例外。"""
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({"I1": _inventory_target()})
        with pytest.raises(ToolArgumentResolutionException):
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_USE_ITEM, {"item_label": "I99"}, ctx,
            )

    def test_spot_graph_use_item_is_dispatch_target(self) -> None:
        """resolver が use_item を None で素通りさせていた regression を防ぐ。"""
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            _SPOT_GRAPH_TOOLS,
        )
        assert TOOL_NAME_SPOT_GRAPH_USE_ITEM in _SPOT_GRAPH_TOOLS


class TestAdapterWithResolver:
    """`_adapt_executor_handler_with_resolver` が resolver と executor を繋ぐ。"""

    def test_resolver_executor(self) -> None:
        """resolver の出力が executor に渡る。"""
        seen_args: Dict[str, Any] = {}

        def fake_executor(pid_int: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
            seen_args.update(args)
            return LlmCommandResultDto(success=True, message="ok")

        resolver = MagicMock()
        resolver.resolve_args.return_value = {
            "item_spec_id": 42, "inner_thought": "ok",
        }
        handler = _WorldLlmWiring._adapt_executor_handler_with_resolver(
            fake_executor, TOOL_NAME_SPOT_GRAPH_USE_ITEM, resolver,
        )
        result = handler(PlayerId(1), {"item_label": "I1"}, _runtime_context({}))
        assert result.success is True
        # resolver が canonical 引数に置き換えたものが exec に届く
        assert seen_args["item_spec_id"] == 42
        assert "item_label" not in seen_args

    def test_resolver_llm_command_result_dto_raises_exception(self) -> None:
        """resolver 例外は名前指定の remediation を持つ LlmCommandResultDto に変換。"""
        def fake_executor(pid_int: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
            pytest.fail("resolver 失敗時に executor が呼ばれてはいけない")

        resolver = MagicMock()
        resolver.resolve_args.side_effect = ToolArgumentResolutionException(
            "ラベルが見つかりません: I99", "INVALID_TARGET_LABEL",
        )
        handler = _WorldLlmWiring._adapt_executor_handler_with_resolver(
            fake_executor, TOOL_NAME_SPOT_GRAPH_USE_ITEM, resolver,
        )
        result = handler(PlayerId(1), {"item_label": "I99"}, _runtime_context({}))
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "I99" in result.message
        # remediation は現在プロンプトに出る「名前」を使うよう示唆する
        assert result.remediation
        assert "所持アイテム" in result.remediation
        assert "アイテム名" in result.remediation
        assert "I1" not in result.remediation
        assert "ラベル" not in result.remediation

    @pytest.mark.parametrize(
        ("tool_name", "expected_phrase", "forbidden_phrase"),
        [
            (TOOL_NAME_SPOT_GRAPH_USE_ITEM, "所持アイテム", "I1"),
            (TOOL_NAME_SPOT_GRAPH_DROP_ITEM, "所持アイテム", "I1"),
            (TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM, "地面に落ちているもの", "I1"),
            (TOOL_NAME_SPOT_GRAPH_GIVE_ITEM, "相手の名前", "P1"),
            (TOOL_NAME_SPOT_GRAPH_ATTACK, "モンスター名", "I1"),
            (TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER, "倒れているプレイヤー", "P1"),
        ],
    )
    def test_resolver_failure_remediation_matches_each_tool(
        self,
        tool_name: str,
        expected_phrase: str,
        forbidden_phrase: str,
    ) -> None:
        """resolver 汎用失敗でも、各 tool の対象種別に合う復帰ヒントを返す。"""
        def fake_executor(pid_int: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
            pytest.fail("resolver 失敗時に executor が呼ばれてはいけない")

        resolver = MagicMock()
        resolver.resolve_args.side_effect = ToolArgumentResolutionException(
            "指定された名前は現在の候補にありません: ghost",
            "INVALID_TARGET_LABEL",
        )
        handler = _WorldLlmWiring._adapt_executor_handler_with_resolver(
            fake_executor, tool_name, resolver,
        )
        result = handler(PlayerId(1), {"inner_thought": "t"}, _runtime_context({}))
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert result.remediation is not None
        assert expected_phrase in result.remediation
        assert forbidden_phrase not in result.remediation
        assert "I1/I2" not in result.remediation
        assert "ラベル" not in result.remediation

    def test_returns_resolver_dispatch_missing_returns_resolver_none_when(
        self,
    ) -> None:
        """resolver dispatch から外れている (設計違反) ケースは、raw args で
        executor に押し付けるのではなく、明示的な error_code で即 surface する
        (code-review HIGH 対応)。raw 渡しだと executor 内で KeyError 等に
        化けて発生源が分かりにくくなる。"""
        called = {"n": 0}

        def fake_executor(pid_int: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
            called["n"] += 1
            return LlmCommandResultDto(success=False, message="raw")

        resolver = MagicMock()
        resolver.resolve_args.return_value = None
        handler = _WorldLlmWiring._adapt_executor_handler_with_resolver(
            fake_executor, "unknown_tool", resolver,
        )
        result = handler(PlayerId(1), {"item_label": "I1"}, _runtime_context({}))
        # executor は呼ばれない
        assert called["n"] == 0
        assert result.success is False
        assert result.error_code == "RESOLVER_DISPATCH_MISSING"
        assert "unknown_tool" in result.message


class TestDispatchTableUsesResolver:
    """dispatch table の item tool handler が実際に resolver を経由する。

    `_wire_missing_spot_graph_tools` が resolver-wrapped adapter を選んでいる
    ことを直接検証する (regression test)。
    """

    def test_all_four_item_tool_resolver_aware_handler(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """use/drop/give/pickup の handler が resolver を呼ぶ動作になっている。

        実体は `_adapt_executor_handler_with_resolver` の closure。closure 名を
        検査する代わりに、不正 label を送って INVALID_TARGET_LABEL が返ること
        (= resolver が動いた証拠) で確認する。
        """
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path)
        wiring = state.llm_wiring
        for tool_name in (
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
        ):
            handler = wiring._tool_handlers.get(tool_name)
            assert handler is not None, f"{tool_name} が dispatch table に無い"
            # 空 targets / 不正 label で呼ぶ → resolver が落ちて
            # INVALID_TARGET_LABEL 系の result_dto が返るはず。
            # 旧コードでは INVALID_ARGUMENT (= resolver を skip して executor が
            # 引数欠落で落ちる) になっていた。
            # PR-α (Y_after_pr639_640 後続): give_item は batch-always
            # (gives: [...]) に統合。単発形式でも配列で渡す。
            if tool_name == TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM:
                args = {"ground_item_label": "G99", "inner_thought": "t"}
            elif tool_name == TOOL_NAME_SPOT_GRAPH_GIVE_ITEM:
                args = {
                    "gives": [
                        {"item_label": "I99", "target_player_label": "P99"}
                    ],
                    "inner_thought": "t",
                }
            else:
                args = {
                    "item_label": "I99",
                    "target_player_label": "P99",
                    "inner_thought": "t",
                }
            ctx = _runtime_context({})
            result = handler(PlayerId(1), args, ctx)
            assert result.success is False
            # resolver 経由なら INVALID_TARGET_LABEL / INVALID_TARGET_KIND が返る
            # (executor 直叩きなら INVALID_ARGUMENT になっていた)
            assert result.error_code in (
                "INVALID_TARGET_LABEL",
                "INVALID_TARGET_KIND",
            ), (
                f"{tool_name}: resolver を経由していない (error_code="
                f"{result.error_code})。executor 直叩きの古い経路に戻った可能性。"
            )


def _monster_target(
    label: str = "M1",
    monster_id: int = 10001,
    display_name: str = "大型カニ",
) -> MonsterToolRuntimeTargetDto:
    return MonsterToolRuntimeTargetDto(
        label=label,
        kind="spot_graph_monster",
        display_name=display_name,
        monster_id=monster_id,
    )


class TestResolveAttack:
    """`SpotGraphArgumentResolver._resolve_attack` が target_label → monster_id 変換できる。

    Issue #618 で発覚した致命的 silent failure の回帰テスト:
    agent が `spot_graph_attack(target_label='大型カニ')` を呼ぶと毎回
    `INVALID_TARGET_LABEL: monster_id が解決されていません` で reject されていた。
    結果として survival_island_v2 で 1 player では大型カニと戦えず、リオ
    (player 3) が tick 32 で攻撃中に死亡、エイダ (player 1) が tick 59 で
    救援中に同じカニに殺害される連鎖死亡が起きた。
    真因: runtime_manager の resolver_targets set に
    TOOL_NAME_SPOT_GRAPH_ATTACK が含まれておらず、attack tool が resolver
    を hook せずに executor 直叩きで起動 → target_label が monster_id に
    変換されない。
    """

    def test_display_name_monster_id_can_resolve(self) -> None:
        """target_label='大型カニ' (= prompt 表示の display_name) で attack 解決。"""
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({"M1": _monster_target(monster_id=10001)})
        out = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            {"target_label": "大型カニ", "inner_thought": "倒すしかない"},
            ctx,
        )
        assert out is not None
        assert out["monster_id"] == 10001
        assert out["target_display_name"] == "大型カニ"
        assert out["inner_thought"] == "倒すしかない"

    def test_label_m1_can_resolve(self) -> None:
        """target_label='M1' でも引ける (= 旧プロンプト経路の後方互換)。"""
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({"M1": _monster_target(monster_id=10001)})
        out = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            {"target_label": "M1", "inner_thought": "t"},
            ctx,
        )
        assert out is not None
        assert out["monster_id"] == 10001

    def test_missing_label_raises_exception(self) -> None:
        """存在しない label は例外。"""
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({"M1": _monster_target()})
        with pytest.raises(ToolArgumentResolutionException) as ei:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_ATTACK,
                {"target_label": "竜", "inner_thought": "t"},
                ctx,
            )
        assert ei.value.error_code == "INVALID_TARGET_LABEL"

    def test_inventory_label_attack_target_invalid_target_kind(self) -> None:
        """monster でなく item の短縮ラベルを直渡すと型違いで弾かれる (= silent success 防止)。

        `target_label='I1'` だと targets dict に直接 hit するが kind が
        inventory_item で attack の期待型 (MonsterToolRuntimeTargetDto) と違う
        → INVALID_TARGET_KIND。`display_name='椰子の実'` での fallback 経路は
        `kind='spot_graph_monster'` で filter されるので、そちらは
        INVALID_TARGET_LABEL を返す (別ケース)。
        """
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({
            "I1": _inventory_target(label="I1", display_name="椰子の実"),
        })
        with pytest.raises(ToolArgumentResolutionException) as ei:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_ATTACK,
                {"target_label": "I1", "inner_thought": "t"},
                ctx,
            )
        assert ei.value.error_code == "INVALID_TARGET_KIND"


class TestAttackDispatchUsesResolver:
    """dispatch table 上 attack tool が resolver-aware handler で登録されている。

    Issue #618 真因の regression test。resolver_targets set から
    TOOL_NAME_SPOT_GRAPH_ATTACK が漏れていると attack は executor 直叩きに
    なり、agent が monster 名を渡しても毎回失敗する (= モンスターと戦えない
    致命的バグ)。本テストが落ちる = resolver_targets から attack が消えた。
    """

    def test_attack_handler_resolver_via(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """不正 label で attack を呼ぶと INVALID_TARGET_LABEL が返る (= resolver を通った証拠)。

        旧コード (resolver 漏れ) では executor 直叩きで `monster_id が解決
        されていません` (= executor 側のメッセージ) が返るが、resolver 経由
        なら resolver_helpers の例外メッセージ「指定された対象ラベルは現在の
        候補にありません」が返る。本テストは error_code を確認する。
        """
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        state = create_world_runtime_session(monkeypatch, tmp_path)
        wiring = state.llm_wiring
        handler = wiring._tool_handlers.get(TOOL_NAME_SPOT_GRAPH_ATTACK)
        assert handler is not None, "attack が dispatch table に無い"
        result = handler(
            PlayerId(1),
            {"target_label": "M99", "inner_thought": "t"},
            _runtime_context({}),
        )
        assert result.success is False
        assert result.error_code in (
            "INVALID_TARGET_LABEL",
            "INVALID_TARGET_KIND",
        ), (
            "attack が resolver を経由していない (error_code="
            f"{result.error_code})。runtime_manager.py の resolver_targets "
            "set から TOOL_NAME_SPOT_GRAPH_ATTACK が抜けた可能性。"
        )

    def test_resolver_targets_set_attack_included(self) -> None:
        """runtime_manager の resolver_targets ハードコード set に attack が含まれる。

        実装ファイルを文字列検索する形式。`resolver_targets = frozenset({...
        TOOL_NAME_SPOT_GRAPH_ATTACK, ...})` のブロックを担保する。
        """
        path = (
            "src/ai_rpg_world/presentation/spot_graph_game/runtime_manager.py"
        )
        content = open(path).read()
        # resolver_targets ブロック内に TOOL_NAME_SPOT_GRAPH_ATTACK が必須
        start = content.find("resolver_targets = frozenset")
        assert start != -1, "resolver_targets 定義が見つからない"
        end = content.find("})", start)
        block = content[start:end]
        assert "TOOL_NAME_SPOT_GRAPH_ATTACK" in block, (
            "resolver_targets に TOOL_NAME_SPOT_GRAPH_ATTACK が無い。"
            "attack は target_label → monster_id 解決が必須なので resolver を hook する必要がある。"
        )
