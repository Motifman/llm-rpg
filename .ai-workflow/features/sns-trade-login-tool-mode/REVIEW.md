---
id: feature-sns-trade-login-tool-mode
title: Sns Trade Login Tool Mode
slug: sns-trade-login-tool-mode
status: review
created_at: 2026-03-21
updated_at: 2026-03-22
branch: feature/sns-trade-login-tool-mode
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
- Files to revisit:
- Decision:
  - 前回指摘の 2 点は解消済み。`MarkNotificationAsReadCommand` に `user_id` が追加され、`NotificationCommandService` で所有者検証が入った。加えて `create_world_query_service(..., sns_mode_session=...)` の実配線を通る `is_sns_mode_active` 回帰テストも追加されている。
  - feature 観点では `flow-ship` に進めてよい。
  - 残余リスクとして、`demos/sns/demo_sns_system.py` の手動操作までは自動テストしていない。

# Release Gate

- Ship ready: yes
- Blocking findings:
  - None
