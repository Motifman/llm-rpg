from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Iterable, Iterator


@dataclass
class ActionArgument:
    name: str
    description: str = ""
    type: str = "free_input"  # "choice" or "free_input"
    candidates: List[str] = field(default_factory=list)

    def to_text(self) -> str:
        if self.type == "choice" and self.candidates:
            candidates_text = ", ".join(map(str, self.candidates))
            return f"- {self.name} (選択式): {self.description} 候補: [{candidates_text}]"
        return f"- {self.name} (自由入力): {self.description}"


@dataclass
class ActionCandidate:
    action_name: str
    action_description: str = ""
    required_arguments: List[ActionArgument] = field(default_factory=list)
    action_type: Optional[str] = None  # e.g. "state_specific" | "spot_specific"
    player_state: Optional[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActionCandidate":
        args: List[ActionArgument] = []
        for a in d.get("required_arguments", []) or []:
            args.append(ActionArgument(
                name=a.get("name", ""),
                description=a.get("description", ""),
                type=a.get("type", "free_input"),
                candidates=a.get("candidates", []) or [],
            ))
        return ActionCandidate(
            action_name=d.get("action_name", ""),
            action_description=d.get("action_description", ""),
            required_arguments=args,
            action_type=d.get("action_type"),
            player_state=d.get("player_state"),
        )

    def to_text(self, index: Optional[int] = None) -> str:
        prefix = f"{index}. " if index is not None else ""
        lines: List[str] = []
        lines.append(f"{prefix}{self.action_name} — {self.action_description}")
        if self.action_type or self.player_state:
            details: List[str] = []
            if self.action_type:
                details.append(f"種別: {self.action_type}")
            if self.player_state:
                details.append(f"状態: {self.player_state}")
            lines.append("  (" + ", ".join(details) + ")")
        if self.required_arguments:
            lines.append("  引数:")
            for arg in self.required_arguments:
                lines.append("    " + arg.to_text())
        else:
            lines.append("  引数: なし")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "action_description": self.action_description,
            "required_arguments": [
                {
                    "name": a.name,
                    "description": a.description,
                    "type": a.type,
                    "candidates": a.candidates,
                } for a in self.required_arguments
            ],
            "action_type": self.action_type,
            "player_state": self.player_state,
        }


@dataclass
class ActionCandidates(Iterable[Dict[str, Any]]):
    items: List[ActionCandidate]

    @staticmethod
    def from_dicts(dict_list: List[Dict[str, Any]]) -> "ActionCandidates":
        return ActionCandidates(items=[ActionCandidate.from_dict(d) for d in dict_list or []])

    def to_text(self) -> str:
        if not self.items:
            return "利用可能なアクションはありません。"
        header = f"利用可能なアクション一覧 ({len(self.items)}件)"
        body_lines: List[str] = [header]
        for i, c in enumerate(self.items, start=1):
            body_lines.append(c.to_text(index=i))
        return "\n".join(body_lines)

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self.items]

    # 既存テスト互換: listのように扱えるようにする
    def __len__(self) -> int:  # type: ignore[override]
        return len(self.items)

    def __iter__(self) -> Iterator[Dict[str, Any]]:  # type: ignore[override]
        for c in self.items:
            yield c.to_dict()

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        return self.items[idx].to_dict()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, list):
            return self.to_dicts() == other
        if isinstance(other, ActionCandidates):
            return self.to_dicts() == other.to_dicts()
        return False


