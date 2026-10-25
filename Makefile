.PHONY: test test-cov test-html lint lint-fix typecheck clean install dev-install help \
	experiment experiment-publish experiment-survival experiment-survival-coop \
	check-no-internal-hostnames build-trace-viewer fuzz-scenario

PYTHON ?= $(shell if [ -x venv/bin/python ]; then echo venv/bin/python; else echo python3; fi)

# デフォルトターゲット
help:
	@echo "利用可能なコマンド:"
	@echo "  make install      - 依存関係をインストール"
	@echo "  make dev-install  - 開発用依存関係をインストール"
	@echo "  make test         - テストを実行"
	@echo "  make lint         - ruff で静的検査 (対象ルールは pyproject.toml)"
	@echo "  make lint-fix     - ruff の自動修正を適用"
	@echo "  make typecheck    - mypy で型検査 (対象は pyproject.toml の files)"
	@echo "  make test-cov     - カバレッジ付きでテストを実行"
	@echo "  make test-html    - HTMLカバレッジレポートを生成"
	@echo "  make clean        - 一時ファイルを削除"
	@echo "  make experiment [EXPERIMENT_PROFILE=memory_jev_mine_v1_v41_thinking_capped_being_memory] [OUT=...]"
	@echo "                                - profile に固定した汎用シナリオ実験"
	@echo "  make experiment-publish ...   - experiment + 自動 gist publish"
	@echo "  make fuzz-scenario [SCENARIO=...] [SEEDS=0-19] [FUZZ_TICKS=40]"
	@echo "                                - でたらめに行動するスタブで回し、例外と内部番号の漏れを探す (実 LLM なし)"
	@echo "  make experiment-survival OUT=..."
	@echo "                                - survival_island_v2 専用 (140 tick / publish 既定)"
	@echo "  make experiment-survival-coop OUT=..."
	@echo "                                - survival_island_v3_coop 専用 (stranded_at_tick=240 / publish 既定)"
	@echo "  make build-trace-viewer RUN_DIR=...  - viewer 3 種 (main + timeline + prompt) を build"

# 依存関係のインストール
install:
	pip install -r requirements.txt

# 開発用依存関係のインストール
dev-install: install
	pip install pytest pytest-cov

# 基本的なテスト実行
test:
	pytest

# 静的検査。検査対象のルールは pyproject.toml の [tool.ruff.lint] にある。
lint:
	uv run --extra dev ruff check src tests scripts

lint-fix:
	uv run --extra dev ruff check --fix src tests scripts

# 型検査。検査対象の文脈は pyproject.toml の [tool.mypy] files にある。
typecheck:
	uv run --extra dev mypy

# カバレッジ付きテスト実行
test-cov:
	pytest --cov=src --cov-report=term-missing

# HTMLカバレッジレポート生成
test-html:
	pytest --cov=src --cov-report=html --cov-report=term
	@echo "HTMLレポートが htmlcov/index.html に生成されました"

# 一時ファイルの削除
clean:
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# 汎用シナリオ実験 (Issue #188 Phase 1d) — 任意 scenario JSON で実行し
# trace.jsonl + report.md + trace.html を出力する。
#
# 使い方:
#   make experiment EXPERIMENT_PROFILE=memory_jev_mine_v1_v41_thinking_capped_being_memory OUT=var/runs/foo-001
#   make experiment EXPERIMENT_PROFILE=smoke_stub OUT=/tmp/llm-rpg-smoke
#   make experiment EXPERIMENT_PROFILE=smoke_stub SCENARIO=data/scenarios/foo.json
#
# 引数 (= make 変数):
#   EXPERIMENT_PROFILE
#                   data/experiment_profiles/<name>.json を読む。
#                   実験フラグ・LLM 設定はここだけに置く。
#   EXPERIMENT_CONFIG
#                   profile ではなく任意 JSON ファイルを読む。
#   SCENARIO        profile の scenario を一時的に上書きするパス。
#   MAX_WORLD_TICKS world_tick がこの値に達したらループ終了 (既定 30)。
#                   旧名 MAX_TICKS は外側 iteration 回数だったが #404 P1 で
#                   意味論を world tick 基準に統一した。
#   OUT             出力ディレクトリ (省略時 var/runs/<scenario>-<timestamp>)
#   PUBLISH         1 で gist 自動 publish (= --publish-gist)
#   OPENAI_API_KEY  実 LLM 接続用の秘密情報。profile には書かない。
MAX_WORLD_TICKS ?=
EXPERIMENT_PROFILE ?= memory_jev_mine_v1_v41_thinking_capped_being_memory
EXPERIMENT_CONFIG ?=
experiment:
	@if [ -n "$(EXPERIMENT_PROFILE)" ] && [ -n "$(EXPERIMENT_CONFIG)" ]; then \
		echo "EXPERIMENT_PROFILE and EXPERIMENT_CONFIG are mutually exclusive"; \
		exit 2; \
	fi
	@mkdir -p var/runs
	@echo "[experiment] profile=$(EXPERIMENT_PROFILE) config=$(EXPERIMENT_CONFIG)"
	uv run python scripts/run_scenario_experiment.py \
		$(if $(EXPERIMENT_PROFILE),--profile $(EXPERIMENT_PROFILE),) \
		$(if $(EXPERIMENT_CONFIG),--experiment-config $(EXPERIMENT_CONFIG),) \
		$(if $(SCENARIO),--scenario $(SCENARIO),) \
		$(if $(MAX_WORLD_TICKS),--max-world-ticks $(MAX_WORLD_TICKS),) \
		$(if $(OUT),--out $(OUT),) \
		$(if $(PUBLISH),--publish-gist,) \
		$(if $(SNAPSHOT_SAVE_DIR),--snapshot-save-dir $(SNAPSHOT_SAVE_DIR),$(if $(OUT),--snapshot-save-dir $(OUT)/snapshots,)) \
		$(if $(SNAPSHOT_LOAD_DIR),--snapshot-load-dir $(SNAPSHOT_LOAD_DIR),)

# Phase 6 (Issue #470): 実験 run の Being snapshot を OUT 配下の snapshots/ に
# 自動保存する shortcut。次回 run-resume で読み込める。
# 使い方:
#   make experiment-with-snapshot SCENARIO=... OUT=var/runs/foo
#   # OUT/snapshots/being_w1_p1.json などが書き出される
experiment-with-snapshot:
	@if [ -z "$(OUT)" ]; then \
		echo "OUT is required for experiment-with-snapshot. e.g. make experiment-with-snapshot SCENARIO=... OUT=var/runs/foo"; \
		exit 2; \
	fi
	$(MAKE) experiment \
		SCENARIO=$(SCENARIO) \
		MAX_WORLD_TICKS=$(MAX_WORLD_TICKS) \
		OUT=$(OUT) \
		PUBLISH=$(PUBLISH) \
		SNAPSHOT_SAVE_DIR=$(OUT)/snapshots

# Phase 6: 別の OUT で同じ scenario を再開する shortcut。
# 使い方:
#   make experiment-resume SCENARIO=... OUT=var/runs/foo_resume \
#     SNAPSHOT_LOAD_DIR=var/runs/foo/snapshots
experiment-resume:
	@if [ -z "$(SNAPSHOT_LOAD_DIR)" ]; then \
		echo "SNAPSHOT_LOAD_DIR is required. e.g. make experiment-resume SCENARIO=... OUT=... SNAPSHOT_LOAD_DIR=var/runs/prev/snapshots"; \
		exit 2; \
	fi
	$(MAKE) experiment \
		SCENARIO=$(SCENARIO) \
		MAX_WORLD_TICKS=$(MAX_WORLD_TICKS) \
		OUT=$(OUT) \
		PUBLISH=$(PUBLISH) \
		SNAPSHOT_LOAD_DIR=$(SNAPSHOT_LOAD_DIR) \
		SNAPSHOT_SAVE_DIR=$(if $(OUT),$(OUT)/snapshots,)

# experiment + secret gist 自動 publish (PUBLISH=1 と同等)
experiment-publish:
	$(MAKE) experiment \
		SCENARIO=$(SCENARIO) MAX_WORLD_TICKS=$(MAX_WORLD_TICKS) OUT=$(OUT) \
		PUBLISH=1

# survival_island_v2 専用のショートカット。
# 4 player + 14 day (= 140 driver tick) + 自動 publish を
# デフォルトに固定して、何度も同じパラメータを打ち直す煩雑さを解消する。
#
# 使い方:
#   make experiment-survival OUT=var/runs/issue390_exp27_off_r1
#
# 上書き可能な変数 (省略時の survival 既定値):
#   MAX_WORLD_TICKS=140  PUBLISH=1
SURVIVAL_MAX_WORLD_TICKS ?= 140
SURVIVAL_PUBLISH ?= 1
experiment-survival:
	$(MAKE) experiment \
		SCENARIO=data/scenarios/survival_island_v2.json \
		MAX_WORLD_TICKS=$(SURVIVAL_MAX_WORLD_TICKS) \
		OUT=$(OUT) \
		PUBLISH=$(SURVIVAL_PUBLISH)

# survival_island_v3_coop 専用のショートカット。
# このシナリオは「漂流確定 (stranded)」が data/scenarios/survival_island_v3_coop.json の
# stranded_at_tick=240 で設計されている (estimated_ticks も 240)。M7 実走で
# --max-world-ticks 200 を指定してしまい、200 で打ち切られ stranded 判定が
# 一度も発火しなかった (協調が破綻したかどうかを観測できなかった) 反省を
# 踏まえ、v3_coop はこのショートカット経由で 240 を既定にして再発を防ぐ。
# 他シナリオ (survival_island_v2 / decay_demo 等) の既定値には影響しない。
#
# 使い方:
#   make experiment-survival-coop OUT=var/runs/m7_coop_r1
#
# 上書き可能な変数 (省略時の coop 既定値):
#   MAX_WORLD_TICKS=240 (= stranded_at_tick)  PUBLISH=1
COOP_MAX_WORLD_TICKS ?= 240
COOP_PUBLISH ?= 1
experiment-survival-coop:
	$(MAKE) experiment \
		SCENARIO=data/scenarios/survival_island_v3_coop.json \
		MAX_WORLD_TICKS=$(COOP_MAX_WORLD_TICKS) \
		OUT=$(OUT) \
		PUBLISH=$(COOP_PUBLISH)

# 内部ホスト名 / 組織 FQDN の混入チェック (docs/security_hosts_policy.md)
check-no-internal-hostnames:
	@./scripts/check_no_internal_hostnames.sh

# Trace viewer の生成 (Issue #188 Phase 1d β + #389 で Phase 3 追加)
# main viewer (viewer.html) に加えて、プレイヤー × tick (timeline.html) と
# prompt の追加 viewer も併せて build する。
# 使い方: make build-trace-viewer RUN_DIR=var/runs/foo
build-trace-viewer:
	@if [ -z "$(RUN_DIR)" ]; then \
		echo "RUN_DIR is required. e.g. make build-trace-viewer RUN_DIR=var/runs/foo"; \
		exit 2; \
	fi
	$(PYTHON) scripts/build_trace_viewer.py $(RUN_DIR)
	@$(PYTHON) scripts/build_timeline_viewer.py $(RUN_DIR) || true
	@$(PYTHON) scripts/build_prompt_viewer.py $(RUN_DIR) || true

# でたらめに行動するスタブで、実 run の前に組み合わせの穴を探す (#1557)。実 LLM を呼ばない。
FUZZ_SCENARIO ?= data/scenarios/mine_village_v1.json
SEEDS ?= 0-19
FUZZ_TICKS ?= 40
fuzz-scenario:
	uv run python scripts/fuzz_scenario_with_random_agents.py \
		--scenario $(if $(SCENARIO),$(SCENARIO),$(FUZZ_SCENARIO)) --seeds $(SEEDS) --ticks $(FUZZ_TICKS) \
		$(if $(FUZZ_PROFILE),--profile $(FUZZ_PROFILE),)
