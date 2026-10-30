"""保存口の固有操作が欠けた実装を、継承元の抽象性に頼らず拒否する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
    SkillLoadoutRepository,
    SkillSpecWriter,
)


class _CommonRepositoryMethods:
    """共通の保存口だけを満たし、スキル固有の検索は実装しない。"""

    def find_by_id(self, entity_id):
        return None

    def find_by_ids(self, entity_ids):
        return []

    def find_all(self):
        return []

    def save(self, entity):
        return entity

    def delete(self, entity_id):
        return False


def _assert_owner_lookup_is_required(repository_type):
    class MissingOwnerLookup(_CommonRepositoryMethods, repository_type):
        pass

    with pytest.raises(TypeError, match="find_by_owner_id"):
        MissingOwnerLookup()

    class CompleteRepository(MissingOwnerLookup):
        def find_by_owner_id(self, owner_id):
            return None

    assert isinstance(CompleteRepository(), repository_type)


def test_skill_loadout_repository_is_abstract() -> None:
    """通常の保存操作を実装しても、装備の所有者検索がないと生成できない。"""
    _assert_owner_lookup_is_required(SkillLoadoutRepository)


def test_skill_deck_progress_repository_is_abstract() -> None:
    """通常の保存操作を実装しても、進行状況の所有者検索がないと生成できない。"""
    _assert_owner_lookup_is_required(SkillDeckProgressRepository)


class _ReplaceOnlyWriter(SkillSpecWriter):
    def replace_spec(self, spec):
        pass


class _DeleteOnlyWriter(SkillSpecWriter):
    def delete_spec(self, skill_id):
        return False


class _CompleteWriter(_ReplaceOnlyWriter, _DeleteOnlyWriter):
    pass


@pytest.mark.parametrize(
    "incomplete_writer,missing_method",
    [(_ReplaceOnlyWriter, "delete_spec"), (_DeleteOnlyWriter, "replace_spec")],
)
def test_skill_spec_writer_is_abstract(incomplete_writer, missing_method) -> None:
    """定義書込み口は置換か削除の片方でも欠けると拒否し、両方あれば生成できる。"""
    with pytest.raises(TypeError, match=missing_method):
        incomplete_writer()

    assert isinstance(_CompleteWriter(), SkillSpecWriter)
