"""UiContextBuilder 用のランタイムターゲット収集コンポーネント。

RuntimeTargetCollector: ToolRuntimeTargetDto を収集し、
最終的な targets 辞書を構築する責務を担う。
"""

from typing import Dict

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto


class RuntimeTargetCollector:
    """ToolRuntimeTargetDto を収集し、targets 辞書を構築する。"""

    def __init__(self) -> None:
        self._targets: Dict[str, ToolRuntimeTargetDto] = {}

    def add(self, label: str, target: ToolRuntimeTargetDto) -> None:
        """単一のターゲットを追加する。重複ラベルの場合は ValueError。"""
        if not isinstance(label, str):
            raise TypeError("label must be str")
        if not isinstance(target, ToolRuntimeTargetDto):
            raise TypeError("target must be ToolRuntimeTargetDto")
        if label in self._targets:
            raise ValueError(f"Duplicate label: {label}")
        self._targets[label] = target

    def add_all(self, targets: Dict[str, ToolRuntimeTargetDto]) -> None:
        """複数のターゲットを一括で追加する。重複ラベルがある場合は上書きする。"""
        if not isinstance(targets, dict):
            raise TypeError("targets must be dict")
        for k, v in targets.items():
            if not isinstance(k, str):
                raise TypeError("targets keys must be str")
            if not isinstance(v, ToolRuntimeTargetDto):
                raise TypeError("targets values must be ToolRuntimeTargetDto")
        self._targets.update(targets)

    def get(self, label: str) -> ToolRuntimeTargetDto | None:
        """指定ラベルのターゲットを返す。存在しない場合は None。"""
        return self._targets.get(label)

    def get_targets(self) -> Dict[str, ToolRuntimeTargetDto]:
        """収集した targets のコピーを返す。"""
        return dict(self._targets)

    def __len__(self) -> int:
        return len(self._targets)
