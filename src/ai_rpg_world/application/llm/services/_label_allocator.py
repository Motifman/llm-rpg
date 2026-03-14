"""UiContextBuilder 用のラベル採番コンポーネント。

LabelAllocator: prefix ごとのカウンタを管理し、一意なラベルを採番する。
SectionBuildResult: セクション描画の戻り値（lines + targets）を表す。
"""

from dataclasses import dataclass
from typing import Dict

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto


# UiContextBuilder が使用する全 label prefix の初期値
DEFAULT_LABEL_PREFIXES = (
    "P", "N", "M", "O", "S", "I", "C", "R", "K", "A",
    "Q", "G", "GI", "GM", "SH", "L", "LA", "D", "T", "H",
    "EK", "ES", "SP", "AW",
)


@dataclass(frozen=True)
class SectionBuildResult:
    """セクション描画の結果。lines と targets を一括で返す。"""

    lines: list[str]
    targets: Dict[str, ToolRuntimeTargetDto]

    def __post_init__(self) -> None:
        if not isinstance(self.lines, list):
            raise TypeError("lines must be list")
        if not isinstance(self.targets, dict):
            raise TypeError("targets must be dict")
        for k, v in self.targets.items():
            if not isinstance(k, str):
                raise TypeError("targets keys must be str")
            if not isinstance(v, ToolRuntimeTargetDto):
                raise TypeError("targets values must be ToolRuntimeTargetDto")

    @staticmethod
    def empty() -> "SectionBuildResult":
        """空の結果を返す。"""
        return SectionBuildResult(lines=[], targets={})


class LabelAllocator:
    """prefix ごとのカウンタを管理し、一意なラベルを採番する。"""

    def __init__(
        self,
        *,
        initial_counters: Dict[str, int] | None = None,
    ) -> None:
        if initial_counters is not None:
            if not isinstance(initial_counters, dict):
                raise TypeError("initial_counters must be dict or None")
            for k, v in initial_counters.items():
                if not isinstance(k, str):
                    raise TypeError("initial_counters keys must be str")
                if not isinstance(v, int) or v < 0:
                    raise TypeError("initial_counters values must be non-negative int")
            self._counters = dict(initial_counters)
        else:
            self._counters = {p: 0 for p in DEFAULT_LABEL_PREFIXES}

    def next(self, prefix: str) -> str:
        """指定 prefix で次のラベルを採番する。"""
        if not isinstance(prefix, str):
            raise TypeError("prefix must be str")
        if not prefix:
            raise ValueError("prefix must not be empty")
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}{self._counters[prefix]}"

    def get_counter(self, prefix: str) -> int:
        """指定 prefix の現在カウントを返す（次の next で使われる値ではない）。"""
        return self._counters.get(prefix, 0)

    def counters_snapshot(self) -> Dict[str, int]:
        """現在のカウンタのスナップショットを返す（読み取り専用用途）。"""
        return dict(self._counters)
