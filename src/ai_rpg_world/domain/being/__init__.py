"""Being bounded context.

Issue #470 Phase 2 (= PR #462 P-1 の入口): 「経験を持つ AI」の主体を第一級の
ドメイン概念として扱うための bounded context。

Phase 2 PR1 (本 PR): 容器の最小骨格のみ
- BeingId (identity)
- BeingIdentity (persona 不変核 = name / first_person)
- Being aggregate root (= BeingId + BeingIdentity)
- BeingRepository interface
- 既存 store とはまだ接続しない (= attachment / memory_refs は後続 PR)

詳細設計: docs/being_architecture_part2_experience_and_scale.md §2.1 (R1)
"""
