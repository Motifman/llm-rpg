"""失敗 DTO に有効ラベルを埋め込んで LLM が失敗から学べるようにする挙動 (F1/F2)。

Issue #154 のデモで Gemma 4 / gpt-5-mini ともに display name (例: ``"操作盤"``) を
``object_label`` に渡し続けて INVALID_TARGET_LABEL を繰り返した。失敗 message に
有効ラベル一覧 + remediation を載せて学習可能にする。

F1 対象:
- INVALID_TARGET_LABEL (interact)
- INVALID_DESTINATION_LABEL (travel_to)
- INVALID_WHISPER (whisper)

F2 対象:
- spot_graph_explore の「新しい発見はなかった」を、可視オブジェクト併記に強化
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
from ai_rpg_world.application.llm.services.llm_client_stub import (
    StubLlmClient,
)
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
    _list_destination_labels,
    _list_object_labels,
    _list_player_labels,
    _list_targets_of_kind,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


def _scenario_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "scenarios"


def _create_relay_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub: StubLlmClient,
):
    """relay_puzzle_demo (制御室に操作盤 OBJ1 がある) でセッション開始。"""
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=_scenario_dir(),
        characters_path=tmp_path / "characters.json",
    )
    char = mgr.create_character(CharacterCreateRequest(name="failure msg テスト"))
    summary = mgr.create_session(
        SessionCreateRequest(
            world_id="relay_puzzle_demo", character_ids=[char.id]
        )
    )
    state = mgr._sessions[summary.session_id]
    state.llm_wiring.llm_client = stub
    return state


def _make_target(label: str, kind: str, display_name: str) -> ToolRuntimeTargetDto:
    """テスト用ヘルパー: 必須フィールドだけ埋めた ``ToolRuntimeTargetDto``。

    本番と同じ frozen dataclass を使うことで、helper の型契約が
    ``ToolRuntimeTargetDto`` に固定されていることを保証する (review HIGH 反映)。
    """
    return ToolRuntimeTargetDto(label=label, kind=kind, display_name=display_name)


class TestListTargetsHelpers:
    """`_list_targets_of_kind` / 各 wrapper の出力形式。"""

    def test_lists_label_with_display_name(self) -> None:
        """ラベルを先頭、display name を括弧内に置く形式で出力する。"""
        targets = {
            "OBJ1": _make_target("OBJ1", "spot_graph_object", "操作盤"),
            "OBJ2": _make_target("OBJ2", "spot_graph_object", "コンソール"),
            "S1": _make_target("S1", "spot_graph_destination", "中央廊下"),
        }
        result = _list_object_labels(targets)
        assert result == "OBJ1 (操作盤) / OBJ2 (コンソール)"

    def test_destination_helper_filters_by_kind(self) -> None:
        """destination 用 helper は object kind を含めない。"""
        targets = {
            "OBJ1": _make_target("OBJ1", "spot_graph_object", "操作盤"),
            "S1": _make_target("S1", "spot_graph_destination", "中央廊下"),
        }
        result = _list_destination_labels(targets)
        assert result == "S1 (中央廊下)"

    def test_player_helper_filters_by_kind(self) -> None:
        """player 用 helper は player kind だけ列挙。"""
        targets = {
            "P1": _make_target("P1", "spot_graph_player", "リン"),
            "OBJ1": _make_target("OBJ1", "spot_graph_object", "操作盤"),
        }
        result = _list_player_labels(targets)
        assert result == "P1 (リン)"

    def test_empty_targets_returns_empty_string(self) -> None:
        """対応 kind が無いと空文字列を返す。"""
        targets = {"S1": _make_target("S1", "spot_graph_destination", "廊下")}
        assert _list_object_labels(targets) == ""
        assert _list_player_labels(targets) == ""

    def test_unknown_kind_is_ignored(self) -> None:
        """未知 kind は出力に含めない (新 kind 追加時の安全側挙動)。"""
        targets = {"X1": _make_target("X1", "some_future_kind", "未来")}
        assert _list_targets_of_kind(targets, "spot_graph_object") == ""


class TestInvalidTargetLabelMessage:
    """INVALID_TARGET_LABEL (spot_graph_interact) の learnable message。"""

    def test_failure_message_enumerates_valid_object_labels(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """LLM が存在しない object 名を渡したとき、有効候補ラベルがメッセージに含まれる。

        PR #441 で display_name fallback が入ったため、relay シナリオで実在する
        ``"操作盤"`` は label と一致して解決されるようになった。本テストは
        「明らかに存在しない名前」を投げて INVALID_TARGET_LABEL ハッピーパスを
        引き続き保証する。
        """
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_interact",
                "arguments": {"object_label": "存在しない架空のオブジェクト_X", "action_name": "電源を入れる"},
            }
        )
        state = _create_relay_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)

        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        # 失敗 label が message に含まれる (元の form)
        assert "存在しない架空のオブジェクト_X" in result.message
        # F1: 有効ラベル列挙が含まれる
        assert "OBJ1" in result.message
        # F1: remediation が "label を指定" を明示
        assert result.remediation is not None
        assert "object_label" in result.remediation


class TestInvalidDestinationLabelMessage:
    """INVALID_DESTINATION_LABEL (spot_graph_travel_to) の learnable message。"""

    def test_destination_にスポット名を渡すと解決されて移動が成功する(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """PR 3 (#227): label miss 時の display_name fallback。LLM が "中央廊下"
        のような不変なスポット名を渡しても、display_name で解決して移動が成功する。

        旧挙動 (label のみ受付) では INVALID_DESTINATION_LABEL で失敗していた
        が、PR 3 で fallback が追加され、本テストは「成功する」ことを保証する
        ように更新された。
        """
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "中央廊下"},
            }
        )
        state = _create_relay_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)

        assert result.success is True
        assert "中央廊下" in result.message

    def test_存在しないラベル_かつ_存在しないスポット名_は_有効候補を列挙して失敗(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """ラベルでも display_name でも解決できない場合は失敗 DTO で有効候補を
        列挙する (F1: 学習可能な失敗メッセージ)。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "未定義の謎のスポット"},
            }
        )
        state = _create_relay_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)

        assert result.success is False
        assert result.error_code == "INVALID_DESTINATION_LABEL"
        # 有効ラベル列挙
        assert "S1" in result.message
        # 期待する display name も併記される
        assert "中央廊下" in result.message
        assert result.remediation is not None
        assert "destination_label" in result.remediation
        # 新 remediation はラベル or スポット名どちらでも OK と案内する
        assert "スポット名" in result.remediation


class TestInvalidWhisperMessage:
    """INVALID_WHISPER の learnable message。"""

    def test_failure_message_with_empty_content_shows_content_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """content 空のとき INVALID_SPEECH_CONTENT を返す (Issue #264 後続: SAY/WHISPER を統合)。"""
        stub_empty = StubLlmClient(
            tool_call_to_return={
                "name": "speak",
                "arguments": {
                    "channel": "whisper",
                    "content": "",
                    "target_label": "P1",
                },
            }
        )
        state = _create_relay_session(monkeypatch, tmp_path, stub_empty)
        target_pid = state.runtime.get_player_ids()[0]
        result_empty = state.llm_wiring.run_turn(target_pid)
        assert result_empty.success is False
        # Issue #264 後続: 統合 dispatch で content 空は INVALID_SPEECH_CONTENT に統一
        assert result_empty.error_code == "INVALID_SPEECH_CONTENT"

    def test_failure_message_with_unknown_target_enumerates_player_labels(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """target_label が解決できないとき、有効な player ラベル候補を提示する。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "speak",
                "arguments": {
                    "channel": "whisper",
                    "content": "テストメッセージ",
                    "target_label": "存在しない宛先",
                },
            }
        )
        state = _create_relay_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)
        assert result.success is False
        assert result.error_code == "INVALID_WHISPER"
        # 宛先が見つからない旨が含まれる
        assert "target_label" in result.message
        # remediation も含む
        assert result.remediation is not None
        assert "target_label" in result.remediation


class TestExploreEmptyMessageAugmented:
    """F2: explore で discovery 0 のとき可視オブジェクト一覧を併記する。"""

    def test_empty_discoveries_lists_visible_objects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """relay_puzzle_demo の制御室 (操作盤あり) で explore → "OBJ1 (操作盤)" を併記。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_explore",
                "arguments": {"inner_thought": "周囲を探す"},
            }
        )
        state = _create_relay_session(monkeypatch, tmp_path, stub)
        # A は spawn=control_room で OBJ1 (操作盤) が見える
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)

        assert result.success is True
        # F2: 単純な「新しい発見はなかった」だけではなく、可視オブジェクトを列挙
        assert "OBJ1" in result.message
        assert "操作盤" in result.message
        # 「object_label に指定」のヒントも含まれる
        assert "object_label" in result.message
