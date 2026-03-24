---
id: feature-trade-selling-pagination-sqlite
title: Trade Selling Pagination Sqlite
slug: trade-selling-pagination-sqlite
status: review
created_at: 2026-03-25
updated_at: 2026-03-25
branch: codex/trade-selling-pagination-sqlite
---

# Review Prompt

Review all files for this feature. Verify DDD boundaries, implementation quality, exception handling, and test thoroughness. Check that there are no placeholder implementations or deferred shortcuts. Compare test strictness with existing strong suites such as `src/domain/trade` and `src/domain/sns`.

# Findings

## Critical

- None

## Major

- None

## Minor

- None

# Follow-up

- Additional phases needed:
-   - None
- Files to revisit:
-   - None
- Decision:
-   - 差し戻し不要。`selling` の ACTIVE 専用ストリーム化、`next_cursor` 意味の整合、in-memory/SQLite の順序・カーソル契約、例外ラップ方針がテストで固定されている。

# Release Gate

- Ship ready: yes
- Blocking findings:
- None
