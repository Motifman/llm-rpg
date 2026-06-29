"""Executor 横断で使う「失敗 DTO の learnable 化」ヘルパー群。

Issue #154 のデモ実走で観測されたように、LLM は失敗 message に有効値が
列挙されていないと同じ間違い (例: ``object_label="操作盤"``) を繰り返す。
ここでは:

- ``ToolRuntimeContextDto.targets`` から kind 別に有効ラベル一覧を組み立てる
  ヘルパー
- 引数欠落 / 型違い の典型的な失敗 DTO を 1 行で構築するファクトリ
- 内部例外を LLM 側に str(e) で漏らさないサニタイズ DTO のファクトリ

を提供する。元々 ``presentation/spot_graph_game/runtime_manager.py`` 内に
private で定義していたものを、Issue #168 で executor 横断 (sns / trade /
spot_graph standalone 等) に展開するため共通モジュールに昇格させた。

依存方向:
    application/llm/services/failure_helpers.py
        ↑ import
    presentation/spot_graph_game/runtime_manager.py     (world_runtime 経路)
    application/llm/services/executors/*.py             (standalone 経路)

application 層内で完結しており、presentation / 各 executor から下向きの
import になるため循環依存はない。
"""

from __future__ import annotations

import logging
from typing import Dict

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.remediation_mapping import get_remediation

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# ToolRuntimeContextDto.targets から有効ラベル一覧を組み立てるヘルパー
# ──────────────────────────────────────────────────────────────────


def list_targets_of_kind(
    targets: Dict[str, ToolRuntimeTargetDto], kind: str
) -> str:
    """``targets`` から指定 kind の項目を ``"L1 (display) / L2 (...)"`` で返す。

    空なら空文字列。LLM 向けに **ラベルを先頭**、display name を括弧内に置く
    順序にする (LLM が ``object_label`` に何を入れるべきかを最初に目に入れる
    ため)。
    """
    items = []
    for label, target in targets.items():
        if target.kind != kind:
            continue
        # ``__edge_*`` などの内部 shadow entry はユーザ向け候補列挙から除外。
        # (travel_to の destination shadow が代表例: edge 名 fallback 用に
        # 同 spot を二重登録しているが、エラー時の候補一覧では本来の spot 名
        # だけを見せたい。Y_after_pr_all_200tick 後続。)
        if label.startswith("__"):
            continue
        display = target.display_name or ""
        items.append(f"{label} ({display})" if display else label)
    return " / ".join(items)


def list_object_labels(targets: Dict[str, ToolRuntimeTargetDto]) -> str:
    """interact 系の object_label 候補を列挙。"""
    return list_targets_of_kind(targets, "spot_graph_object")


def list_destination_labels(targets: Dict[str, ToolRuntimeTargetDto]) -> str:
    """travel_to の destination_label 候補を列挙。"""
    return list_targets_of_kind(targets, "spot_graph_destination")


def list_player_labels(targets: Dict[str, ToolRuntimeTargetDto]) -> str:
    """whisper の target_label 候補 (同 spot の他プレイヤー)。"""
    return list_targets_of_kind(targets, "spot_graph_player")


# ──────────────────────────────────────────────────────────────────
# 失敗 DTO ファクトリ
#
# LLM-facing message は短く、remediation は ``DEFAULT_REMEDIATION_BY_ERROR_CODE``
# 経由で取得する。error_code を渡すことで、orchestrator 側で
# ``is_reschedulable_error_code`` の判定にも乗る。
# ──────────────────────────────────────────────────────────────────


def build_invalid_arg_failure(
    *,
    arg_name: str,
    detail: str,
    error_code: str = "INVALID_ARGUMENT",
) -> LlmCommandResultDto:
    """引数欠落 / 型違い系の失敗を learnable な形式で返すファクトリ。

    例:
        return build_invalid_arg_failure(
            arg_name="destination_spot_id",
            detail="正の整数を指定してください",
        )

    結果メッセージ:
        ``"引数 destination_spot_id が不正です: 正の整数を指定してください"``

    Args:
        arg_name: 不正だった引数名 (LLM が prompt 内で見られる形式)
        detail: 何が悪かったかの短い説明 (具体的な期待値)
        error_code: 任意上書き。既定 ``"INVALID_ARGUMENT"``
    """
    return LlmCommandResultDto(
        success=False,
        message=f"引数 {arg_name} が不正です: {detail}",
        error_code=error_code,
        remediation=get_remediation(error_code),
    )


def build_unknown_label_failure(
    *,
    label_kind: str,
    given_label: str,
    valid_labels_summary: str,
    error_code: str = "INVALID_TARGET_LABEL",
) -> LlmCommandResultDto:
    """ラベル解決失敗 (UNKNOWN_LABEL カテゴリ) の learnable 失敗 DTO。

    PR #167 で world_runtime 経路に入れたパターンを共通化したもの。message に
    有効ラベル一覧を併記し、LLM が次の試行で正しい label を選べるようにする。

    Args:
        label_kind: ``"object_label"`` / ``"destination_label"`` /
            ``"target_label"`` 等、LLM が使う argument 名
        given_label: LLM が渡してきた (解決できなかった) 値
        valid_labels_summary: ``list_*_labels`` 系ヘルパーの出力。空のとき
            は「該当ラベル無し」と読み替える
        error_code: 任意上書き。既定 ``"INVALID_TARGET_LABEL"``
    """
    valid_part = (
        f"有効な {label_kind}: {valid_labels_summary}"
        if valid_labels_summary
        else f"この場所には有効な {label_kind} がありません"
    )
    return LlmCommandResultDto(
        success=False,
        message=(
            f"{label_kind}={given_label!r} を解決できませんでした。{valid_part}"
        ),
        error_code=error_code,
        remediation=get_remediation(error_code),
    )


def build_sanitized_exception_failure(
    *,
    exc: BaseException,
    log_context: str,
    public_message: str,
    error_code: str = "SYSTEM_ERROR",
) -> LlmCommandResultDto:
    """内部例外を LLM に str(e) で漏らさないサニタイズ DTO。

    PR #156 で発見された path/secrets 漏洩 + prompt injection 経路の
    再発防止用ファクトリ。本ファクトリ呼び出しで:

    - サーバログには ``logger.exception(log_context)`` で全コンテキストを残す
    - LLM への message は固定文言 ``public_message`` のみ
    - error_code は ``DEFAULT_REMEDIATION_BY_ERROR_CODE`` に登録済のものを使う

    Args:
        exc: 捕捉した例外
        log_context: ログのコンテキスト文字列 (player_id / tool_name 等)
        public_message: LLM に返す固定文言 (str(exc) を含めない)
        error_code: 任意上書き。既定 ``"SYSTEM_ERROR"``
    """
    logger.exception("%s: %s", log_context, type(exc).__name__)
    return LlmCommandResultDto(
        success=False,
        message=public_message,
        error_code=error_code,
        remediation=get_remediation(error_code),
    )


__all__ = [
    "list_targets_of_kind",
    "list_object_labels",
    "list_destination_labels",
    "list_player_labels",
    "build_invalid_arg_failure",
    "build_unknown_label_failure",
    "build_sanitized_exception_failure",
]
