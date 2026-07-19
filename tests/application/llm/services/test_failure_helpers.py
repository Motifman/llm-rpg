"""``application/llm/services/failure_helpers`` の単体テスト (PR-0)。

PR #167 (world_runtime 経路) で導入したラベル列挙ヘルパーを executor 横断
共通モジュール化し、その挙動を本テストで保証する。

加えて新規ファクトリ:
- ``build_invalid_arg_failure``
- ``build_unknown_label_failure``
- ``build_sanitized_exception_failure``

の DTO 構築仕様もここで固定する。
"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
from ai_rpg_world.application.llm.services.failure_helpers import (
    build_invalid_arg_failure,
    build_sanitized_exception_failure,
    build_unknown_label_failure,
    list_destination_labels,
    list_object_labels,
    list_player_labels,
    list_targets_of_kind,
)


def _make_target(label: str, kind: str, display_name: str) -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(
        label=label, kind=kind, display_name=display_name
    )


class TestListTargetsOfKind:
    """``list_targets_of_kind`` の出力形式と kind フィルタ。"""

    def test_lists_label_with_display_name(self) -> None:
        """候補一覧はプロンプトに表示される名前だけを quote 付きで出力する。"""
        targets = {
            "OBJ1": _make_target("OBJ1", "spot_graph_object", "操作盤"),
            "OBJ2": _make_target("OBJ2", "spot_graph_object", "コンソール"),
            "S1": _make_target("S1", "spot_graph_destination", "中央廊下"),
        }
        assert list_object_labels(targets) == '"操作盤" / "コンソール"'

    def test_destination_helper_filters_by_kind(self) -> None:
        """移動先候補も旧 S1 ではなくスポット名を出す。"""
        targets = {
            "OBJ1": _make_target("OBJ1", "spot_graph_object", "操作盤"),
            "S1": _make_target("S1", "spot_graph_destination", "中央廊下"),
        }
        assert list_destination_labels(targets) == '"中央廊下"'

    def test_player_helper_filters_by_kind(self) -> None:
        """プレイヤー候補も旧 P1 ではなく名前を出す。"""
        targets = {
            "P1": _make_target("P1", "spot_graph_player", "B"),
            "OBJ1": _make_target("OBJ1", "spot_graph_object", "操作盤"),
        }
        assert list_player_labels(targets) == '"B"'

    def test_empty_targets_returns_empty_string(self) -> None:
        targets = {"S1": _make_target("S1", "spot_graph_destination", "廊下")}
        assert list_object_labels(targets) == ""
        assert list_player_labels(targets) == ""

    def test_target_without_display_name_is_hidden(self) -> None:
        """display_name が空の内部候補は、旧ラベル露出を避けるため一覧から隠す。"""
        targets = {"OBJ1": _make_target("OBJ1", "spot_graph_object", "")}
        assert list_object_labels(targets) == ""

    def test_unknown_kind_returns_empty(self) -> None:
        targets = {"X1": _make_target("X1", "future_kind", "未来")}
        assert list_targets_of_kind(targets, "spot_graph_object") == ""


class TestBuildInvalidArgFailure:
    """``build_invalid_arg_failure`` の DTO 構築仕様。"""

    def test_basic_failure_dto(self) -> None:
        """message に arg_name と detail が入り、error_code/remediation が
        DEFAULT_REMEDIATION_BY_ERROR_CODE 経由で埋まる。"""
        dto = build_invalid_arg_failure(
            arg_name="destination_spot_id",
            detail="正の整数を指定してください",
        )
        assert dto.success is False
        assert dto.error_code == "INVALID_ARGUMENT"
        assert "destination_spot_id" in dto.message
        assert "正の整数" in dto.message
        # remediation_mapping に登録されているので非空文言が返る
        assert dto.remediation is not None
        assert dto.remediation != ""

    def test_custom_error_code(self) -> None:
        """error_code を override すれば remediation もその code 用が引かれる。"""
        dto = build_invalid_arg_failure(
            arg_name="trade_ref",
            detail="必須",
            error_code="TRADE_ARG_MISSING",
        )
        assert dto.error_code == "TRADE_ARG_MISSING"
        assert dto.remediation is not None
        # remediation に「取引ツール」が含まれる (= TRADE_ARG_MISSING の文言)
        assert "取引" in dto.remediation


class TestBuildUnknownLabelFailure:
    """``build_unknown_label_failure`` の learnable 失敗 DTO。"""

    def test_lists_valid_labels_in_message(self) -> None:
        """LLM が間違いラベルを使ったとき、有効ラベル一覧が message に入る。"""
        dto = build_unknown_label_failure(
            label_kind="object_label",
            given_label="操作盤",
            valid_labels_summary='"操作盤" / "コンソール"',
        )
        assert dto.success is False
        assert dto.error_code == "INVALID_TARGET_LABEL"
        # 与えられた間違い label
        assert "'操作盤'" in dto.message or "操作盤" in dto.message
        # 有効候補一覧
        assert '"操作盤"' in dto.message
        assert '"コンソール"' in dto.message

    def test_empty_valid_labels_says_none_available(self) -> None:
        """有効候補が空のときは候補なしを明示。"""
        dto = build_unknown_label_failure(
            label_kind="object_label",
            given_label="操作盤",
            valid_labels_summary="",
        )
        assert "有効な object_label" in dto.message or "ありません" in dto.message

    def test_destination_label_kind(self) -> None:
        """label_kind は travel_to 系でも使える (汎用)。"""
        dto = build_unknown_label_failure(
            label_kind="destination_label",
            given_label="中央廊下",
            valid_labels_summary='"中央廊下"',
        )
        assert "destination_label" in dto.message
        assert '"中央廊下"' in dto.message


class TestBuildSanitizedExceptionFailure:
    """``build_sanitized_exception_failure`` の セキュリティ仕様。"""

    def test_str_exc_is_not_leaked_to_message(self, caplog) -> None:
        """例外オブジェクトの str(exc) は LLM 向け message に含めない。"""

        class _SensitiveError(Exception):
            pass

        exc = _SensitiveError(
            "/home/user/secret_path: API_KEY=sk-xxxxxxxx"
        )
        with caplog.at_level(
            logging.ERROR,
            logger="ai_rpg_world.application.llm.services.failure_helpers",
        ):
            dto = build_sanitized_exception_failure(
                exc=exc,
                log_context="tool=foo player=42",
                public_message="ツール実行中に内部エラーが発生しました。",
            )

        assert dto.success is False
        assert dto.error_code == "SYSTEM_ERROR"
        assert dto.message == "ツール実行中に内部エラーが発生しました。"
        # 漏洩していないこと (server log にだけ残る)
        assert "/home/user/secret_path" not in dto.message
        assert "API_KEY" not in dto.message
        assert "sk-xxxxxxxx" not in dto.message
        # サーバログには文脈が残る
        assert any(
            "tool=foo player=42" in r.message for r in caplog.records
        )

    def test_remediation_loaded_from_mapping(self) -> None:
        """error_code に応じた remediation が引かれる (SYSTEM_ERROR 既定)。"""
        dto = build_sanitized_exception_failure(
            exc=RuntimeError("x"),
            log_context="ctx",
            public_message="エラー発生",
        )
        assert dto.remediation is not None
        assert dto.remediation != ""

    def test_custom_error_code(self) -> None:
        """error_code を上書きできる。"""
        dto = build_sanitized_exception_failure(
            exc=ValueError("y"),
            log_context="ctx",
            public_message="ホニャララ",
            error_code="INVALID_ARGUMENT",
        )
        assert dto.error_code == "INVALID_ARGUMENT"
