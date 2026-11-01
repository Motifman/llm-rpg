# 刻限に達した tick では追加の手番を起こさない

エージェントに見える残り時間、ゲームの終了判定、post-tick hook の手番入口は、同じ world tick に基づく。`TICK_LIMIT=30` なら tick 30 の手番より前に時間切れを確定し、tick 25 から snapshot を再開した場合の残り時間は 5 と表示する。これにより、復元後や刻限ちょうどの hook で余分な LLM 行動が起きず、時間切れの結果が勝利操作で変わらない。

`tests/demos/test_single_relic_contention_demo_scenario.py::test_tick_limit_is_checked_before_the_post_tick_turn` は hook 内から実際の `check_game_end()` を呼び、遺物獲得による勝利を試みる。`tests/demos/test_world_runtime_tick_budget.py::test_budget_uses_world_tick_restored_from_snapshot` は tick 25 の復元後に残り 55 を確認する。
