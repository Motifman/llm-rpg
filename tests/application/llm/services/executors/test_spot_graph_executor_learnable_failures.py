"""Issue #168 PR-2: ``SpotGraphToolExecutor`` の失敗 DTO が learnable に
なっているか検証する。

PR #167 (world_runtime 経路) と PR #170 (sns/trade enter) で確立した不変条件
を spot_graph 経路にも展開する:

- 失敗 DTO に ``error_code`` が必ず付く
- 失敗 DTO に ``remediation`` が必ず付く
- 例外メッセージ (path / 内部 ID 含みうる) は LLM 向け message に漏らさない
- 引数バリデーション失敗は ``build_invalid_arg_failure`` の learnable な形式
  (arg 名と期待値を message に含む)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    AvailableSlotLookup,
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)


def _build_executor(
    *, sync_action_groups: tuple[SynchronizedActionGroup, ...] = ()
) -> SpotGraphToolExecutor:
    """最小限の wiring で executor を構築する (state mutation はテストしない)。

    `time_provider` を渡すのは、`prepare_action` が「登録できない構成では成功を
    返さない」ようになったため (#853)。ここを None のままにすると、協力操作の
    正の対照が「タイミングを合わせられない」で落ちる。
    """
    movement = MagicMock()
    services = SpotGraphWorldServices(
        interaction=MagicMock(),
        exploration=MagicMock(),
        world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
        game_end_evaluator=MagicMock(),
        exploration_progress=MagicMock(),
        movement=movement,
        simulation=None,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        sync_action_groups=sync_action_groups,
        time_provider=MagicMock(
            get_current_tick=MagicMock(return_value=MagicMock(value=1))
        ),
    )


def _sync_group() -> SynchronizedActionGroup:
    """prepare_action を有効化する最小の同期グループ定義。"""
    return SynchronizedActionGroup(
        group_id="test_sync",
        required_action_names=("left", "right"),
        window_ticks=2,
        on_complete=(MagicMock(),),
    )


def _assert_learnable_failure(result, expected_error_code: str | None = None) -> None:
    """failure DTO の最低限の体裁 (error_code + remediation 必須) を確認。"""
    assert result.success is False
    assert result.error_code, f"error_code が空: {result!r}"
    if expected_error_code is not None:
        assert result.error_code == expected_error_code
    assert result.remediation, f"remediation が空: {result!r}"


class TestTravelToInvalidArgs:
    """``destination_spot_id`` の検証失敗。"""

    def test_negative_destination_is_learnable(self) -> None:
        """負の destination_spot_id は INVALID_ARGUMENT で learnable に返る。"""
        executor = _build_executor()
        result = executor._travel_to(player_id=1, args={"destination_spot_id": -1})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "destination_spot_id" in result.message
        # 期待値 (正の整数) が message に含まれる
        assert "正の整数" in result.message

    def test_zero_destination_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._travel_to(player_id=1, args={"destination_spot_id": 0})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")

    def test_non_integer_destination_is_learnable(self) -> None:
        """non-int も learnable な形式で返る。"""
        executor = _build_executor()
        result = executor._travel_to(
            player_id=1, args={"destination_spot_id": "abc"}
        )
        _assert_learnable_failure(result, "INVALID_ARGUMENT")


class TestSetSubLocationInvalidArgs:
    def test_non_integer_sub_location_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._set_sub_location(player_id=1, args={"sub_location_id": "x"})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "sub_location_id" in result.message


class TestInteractInvalidArgs:
    def test_missing_action_name_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._interact(
            player_id=1, args={"object_id": 5, "action_name": ""}
        )
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "action_name" in result.message

    def test_zero_object_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._interact(
            player_id=1, args={"object_id": 0, "action_name": "examine"}
        )
        _assert_learnable_failure(result, "INVALID_ARGUMENT")


class TestUseItemInvalidArgs:
    def test_missing_item_spec_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._use_item(player_id=1, args={})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "item_spec_id" in result.message

    def test_non_integer_item_spec_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._use_item(player_id=1, args={"item_spec_id": "foo"})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")


class TestUseItemInventoryResolutionFailures:
    """use_item の解決段階で、想定内の失敗と配線ミスを区別して返す。"""

    def test_missing_owned_item_is_item_not_found_not_system_error(self) -> None:
        """指定名のアイテムを持っていないときは、SYSTEM_ERROR ではなく ITEM_NOT_FOUND で返る。"""
        executor = _build_executor()
        inv = MagicMock(spec=PlayerInventoryAggregate)
        inv.iter_occupied_slots.return_value = []
        inv.find_available_slot_by_item_spec_id_and_spoilage.return_value = (
            AvailableSlotLookup()
        )
        executor._player_inventory_repository.find_by_id.return_value = inv

        result = executor._use_item(player_id=1, args={"item_spec_id": 1})

        _assert_learnable_failure(result, "ITEM_NOT_FOUND")
        assert "持っていません" in result.message
        assert result.error_code != "SYSTEM_ERROR"

    def test_unexpected_item_lookup_exception_is_traced_without_leaking_to_message(self) -> None:
        """item_repository の配線ミスは LLM には汎用文、trace には例外型と発生段階を残す。"""
        executor = _build_executor()
        inv = MagicMock(spec=PlayerInventoryAggregate)
        inv.iter_occupied_slots.return_value = []
        inv.find_available_slot_by_item_spec_id_and_spoilage.return_value = (
            AvailableSlotLookup(
                slot_id=SlotId(1), item_instance_id=ItemInstanceId(7001)
            )
        )
        executor._player_inventory_repository.find_by_id.return_value = inv
        executor._item_repository.find_by_id.side_effect = RuntimeError(
            "internal wiring token=secret"
        )

        result = executor._use_item(player_id=1, args={"item_spec_id": 1})

        _assert_learnable_failure(result, "SYSTEM_ERROR")
        assert "internal wiring" not in result.message
        assert "token=secret" not in result.message
        assert result.trace_payload is not None
        assert result.trace_payload["tool_exception_location"] == "_use_item"
        assert result.trace_payload["tool_exception_stage"] == "item_lookup"
        assert result.trace_payload["tool_exception_type"] == "RuntimeError"


class TestPrepareActionRejectsAnUndeclaredName:
    """宣言されていない協力操作を「準備できた」と返さない。

    #853 の中核。旧実装は非空文字列なら何でも ``success=True`` で

        アクション「〇〇」の準備をした。他のプレイヤーが対応する操作を実行できる
        ようになった。

    と返していた。一方 ``_maybe_register_sync_prepare`` は一致する group が無ければ
    黙って ``return`` するので、**何も登録されないのに準備できたと伝わる**。
    エージェントは起きない出来事を待ち続ける。

    さらに旧実装は `action_id` を要求していたので、その名前はプロンプトのどこにも
    表示されず、エージェントは**推測するしかなかった**。推測が成功として返るので、
    失敗に気づく手段が無い。3 つ重なって完全な静かな失敗になっていた。
    """

    def test_an_undeclared_name_is_a_learnable_failure(self) -> None:
        """宣言に無い名前を渡すと、成功ではなく学習可能な失敗が返る。"""
        executor = _build_executor(sync_action_groups=(_sync_group(),))

        result = executor._prepare_action(
            player_id=1, args={"action_name": "レバーを引く"}
        )

        _assert_learnable_failure(result, "INTERACTION_ACTION_NOT_FOUND")

    def test_it_does_not_claim_that_others_can_now_act(self) -> None:
        """失敗時に「相方が合わせれば動く」と受け取れる文を返さない。

        旧実装はここで「他のプレイヤーが対応する操作を実行できるようになった」と
        返していた。**それが嘘である**ことがこの issue の実害だった。
        """
        executor = _build_executor(sync_action_groups=(_sync_group(),))

        result = executor._prepare_action(
            player_id=1, args={"action_name": "レバーを引く"}
        )

        assert "できるようになった" not in result.message
        assert "合わせれば動く" not in result.message

    def test_the_failure_lists_the_names_that_do_work(self) -> None:
        """使える操作名を添える。次に何を渡せばよいかが分かる形にする。

        実験 #26 で interact が同じ形で詰まった (ad-hoc な名前を発明しても汎用の
        失敗しか返らず、定義済みの名前を学習できなかった)。同じ轍を踏まない。
        """
        executor = _build_executor(sync_action_groups=(_sync_group(),))

        result = executor._prepare_action(
            player_id=1, args={"action_name": "レバーを引く"}
        )

        assert "left" in result.message
        assert "right" in result.message

    def test_a_declared_name_still_succeeds(self) -> None:
        """宣言済みの名前は従来どおり成功する (正の対照)。

        これが無いと「常に失敗させる」実装でも上の 3 件が通ってしまう。
        """
        executor = _build_executor(sync_action_groups=(_sync_group(),))

        result = executor._prepare_action(player_id=1, args={"action_name": "left"})

        assert result.success is True, result.message
        assert "left" in result.message


class TestPrepareActionDoesNotSucceedWhenItCannotRegister:
    """登録できない構成では、準備できたと返さない。"""

    def test_a_missing_time_provider_is_a_visible_failure(self) -> None:
        """`time_provider` が無い構成では、宣言済みの名前でも成功を返さない。

        `_maybe_register_sync_prepare` は `time_provider` が None のとき黙って
        return する。そして `runtime_manager` は
        ``time_provider=getattr(runtime, "_time_provider", None)`` で渡すので、
        **属性名が変われば静かに None になる**。

        以前はそのとき「準備をした」と成功を返しつつ、同期登録も相方への観測も
        起きなかった。#853 で直した嘘と同じ形が配線の側から再発する経路なので、
        ここで塞ぐ。
        """
        executor = _build_executor(sync_action_groups=(_sync_group(),))
        executor._time_provider = None

        result = executor._prepare_action(player_id=1, args={"action_name": "left"})

        _assert_learnable_failure(result)
        assert "準備をした" not in result.message


class TestPrepareActionValidationLeak:
    """``_prepare_action`` の ValueError が str(exc) で LLM に漏れないこと。"""

    def test_prepare_action_without_sync_groups_is_unsupported_tool(self) -> None:
        """同期グループが無い構成で無理に prepare_action を呼んでも、学習可能に拒否する。"""
        executor = _build_executor()

        result = executor._prepare_action(player_id=1, args={"action_name": "left"})

        _assert_learnable_failure(result, "UNSUPPORTED_TOOL")
        assert "同期アクション" in result.message

    def test_empty_action_name_is_learnable_arg_failure(self) -> None:
        """空の action_name は build_invalid_arg_failure 経由で安全に返る。

        #853 で引数を `action_id` から `action_name` へ改称した。ID を渡させると
        プロンプトに出ていないものを指定させることになり、推測を誘う
        (design_decisions #3)。以前ここは `"action_id" in result.message` を
        求めていたが、その引数名自体が無くなった。
        """
        executor = _build_executor(sync_action_groups=(_sync_group(),))
        result = executor._prepare_action(player_id=1, args={"action_name": ""})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "action_name" in result.message

    def test_value_error_is_sanitized(self, caplog) -> None:
        """registry が ValueError を投げても、str(exc) は LLM 向け message に出ない。

        PR #170 と同じ pattern: 内部 path/ID を含みうる ValueError メッセージ
        を漏らさず、サーバログには warning レベルで全文脈を残す。
        """
        executor = _build_executor(sync_action_groups=(_sync_group(),))
        # PreparedActionRegistry.prepare をモンキーパッチして機微 ValueError を投げる
        sensitive = "/internal/secret_action_path: token=xyz"
        import ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor as mod

        class _StubRegistry:
            def __init__(self, *_, **__): ...
            def prepare(self, **__):
                raise ValueError(sensitive)

        original = mod.PreparedActionRegistry
        mod.PreparedActionRegistry = _StubRegistry  # type: ignore[attr-defined]
        try:
            with caplog.at_level(
                logging.WARNING,
                logger="ai_rpg_world.application.llm.services.failure_helpers",
            ):
                result = executor._prepare_action(
                    player_id=1, args={"action_name": "left"}
                )
        finally:
            mod.PreparedActionRegistry = original  # type: ignore[attr-defined]

        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        # 機微情報が message に漏れていない
        assert "/internal/secret_action_path" not in result.message
        assert "token=xyz" not in result.message
        # 操作名自体は LLM が次の試行に使えるよう残してよい (表示されている名前
        # なので、内部 ID を漏らすことにはならない)。
        assert "left" in result.message


class TestInventoryNotFound:
    """インベントリ未取得時の失敗。"""

    def test_use_item_returns_learnable_on_missing_inventory(self) -> None:
        executor = _build_executor()
        executor._player_inventory_repository.find_by_id.return_value = None
        result = executor._use_item(player_id=1, args={"item_spec_id": 1})
        _assert_learnable_failure(result, "PLAYER_NOT_FOUND")

    # PR-θ1 (経路統合) で削除: 旧 test は _travel_to 内の inventory check を
    # 前提としていたが、統合後の _travel_to は inventory check を持たず
    # runtime.do_move に委譲する (旧 _handle_travel_to も持っていなかった)。
    # inventory None は runtime.do_move が空 owned で silent に扱うので、
    # LLM 向け PLAYER_NOT_FOUND は返らない。この挙動は仕様。
