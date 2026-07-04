"""`spot_graph_listen` ツールの統合テスト (Phase 5 PR-2, PR-θ4 で改訂)。

PR-θ4 (経路統合) 後: SpotGraphToolExecutor._listen は `runtime.do_listen` を
呼ぶ薄い wrapper になった。旧経路 (`spot_graph_repository.emit_listen_carefully`
+ `event_publisher.publish_all` を executor が直接叩く) は削除され、do_listen
がそれらを面倒見る単一の真実源になっている。

本 test は新経路の contract を検証する:
- runtime.do_listen が返す event_count に応じた prose を組み立てる
- runtime 未注入時は NOT_WIRED を返す (test 構成のみの経路)
- get_handlers() に listen が含まれる (dispatch registration の smoke check)

runtime.do_listen の中身 (emit_listen_carefully + _process_graph_events で
SpotSoundHeardEvent が pipeline に流れる) は
``tests/integration/test_world_runtime_current_runtime_contract.py`` 系の
integration test で保証されている。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)


def _build_executor(*, runtime) -> SpotGraphToolExecutor:
    """PR-θ4 経路統合後: `_listen` は runtime.do_listen に委譲するので、
    services / spot_graph_repo などは executor で使わない (MagicMock で埋める)。
    """
    services = MagicMock()
    services.movement = MagicMock()  # constructor で is None チェックがあるため
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        event_publisher=MagicMock(),
        spot_graph_repository=MagicMock(),
        runtime=runtime,
    )


class TestListenCarefullyHappyPath:
    """runtime.do_listen が返す件数に応じた prose が組み立てられる。"""

    def test_2_件の音が観測されたら_件数入り_message(self) -> None:
        runtime = MagicMock()
        runtime.do_listen.return_value = 2
        executor = _build_executor(runtime=runtime)

        result = executor._listen(7, {"inner_thought": "聞いてみる"})

        assert result.success is True
        assert "2 箇所" in result.message
        # PlayerId(7) で do_listen が呼ばれた
        args, _ = runtime.do_listen.call_args
        assert int(args[0].value) == 7

    def test_1_件の音が観測されたら_単数形_message(self) -> None:
        runtime = MagicMock()
        runtime.do_listen.return_value = 1
        executor = _build_executor(runtime=runtime)

        result = executor._listen(7, {"inner_thought": "聞いてみる"})

        assert result.success is True
        assert "1 箇所" not in result.message
        assert "周囲の音が観測として届いた" in result.message


class TestListenCarefullySilent:
    """全 spot SILENT / 減衰しきり: 「何も聞こえなかった」message。"""

    def test_0_件なら_何も聞こえなかった(self) -> None:
        runtime = MagicMock()
        runtime.do_listen.return_value = 0
        executor = _build_executor(runtime=runtime)

        result = executor._listen(7, {"inner_thought": ""})

        assert result.success is True
        assert "何も聞こえなかった" in result.message


class TestListenCarefullyUnwired:
    """runtime 未注入時は NOT_WIRED。"""

    def test_runtime_未注入_は_NOT_WIRED(self) -> None:
        executor = _build_executor(runtime=None)

        result = executor._listen(7, {"inner_thought": ""})

        assert result.success is False
        assert result.error_code == "NOT_WIRED"


class TestListenCarefullyHandlerRegistration:
    """get_handlers() に listen ハンドラが登録される。"""

    def test_get_handlers_に_listen_が_登録される(self) -> None:
        services = MagicMock()
        services.movement = MagicMock()
        executor = SpotGraphToolExecutor(
            spot_graph_world_services=services,
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
        )
        handlers = executor.get_handlers()
        assert "listen" in handlers
