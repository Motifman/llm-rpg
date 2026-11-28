from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import final

from ai_rpg_world.application.being.being_memory_snapshot_service import BeingMemorySnapshotService
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.being_repository import BeingRepository
from ai_rpg_world.game_world.domain.value_object import PersonId

_logger = logging.getLogger(__name__)


@final
@dataclasses.dataclass(frozen=True)
class WrittenMemoryFiles:
    paths: tuple[Path, ...]
    failures: int


@final
class BeingMemoryFiles:
    """run の終わりに、Being ごとの人柄と記憶を 1 人 1 ファイルで残す。読み込みには使わない (#2322)。"""

    def __init__(self, directory: Path, *, beings: BeingRepository, memories: BeingMemorySnapshotService) -> None:
        self._directory = directory
        self._beings = beings
        self._memories = memories

    def write(self, people: Iterable[tuple[PersonId, str, BeingId]]) -> WrittenMemoryFiles:
        listed = tuple(people)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        # 置き場所を作れなくても、遊びを止めた本当の理由を上書きしない
        except OSError:
            _logger.warning("failed to make %s", self._directory, exc_info=True)
            return WrittenMemoryFiles((), len(listed))
        paths: list[Path] = []
        failures = 0
        for person, name, being_id in listed:
            # 1 人ぶん書けなくても、ほかの人の記憶は残す
            try:
                paths.append(self._write_one(person, name, being_id))
            except Exception:
                failures += 1
                _logger.warning("failed to write the memory of %s", person.value, exc_info=True)
        return WrittenMemoryFiles(tuple(paths), failures)

    def _write_one(self, person: PersonId, name: str, being_id: BeingId) -> Path:
        being = self._beings.get(being_id)
        attachment = being.attachment
        payload = {
            "person": {"person_id": person.value, "name": name},
            "being": {
                "being_id": being_id.value,
                "persona": dataclasses.asdict(being.persona),
                "attachment": None if attachment is None else dataclasses.asdict(attachment),
            },
            "memory": json.loads(self._memories.capture(being_id)),
        }
        path = self._directory / f"{person.value}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
