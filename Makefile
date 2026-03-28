.PHONY: test test-cov test-html clean install dev-install help \
	web-demo-db web-demo-db-reset web-backend web-frontend-install \
	web-frontend-test web-frontend-build web-frontend

WEB_GAME_DB ?= var/game/ai_rpg_world.db
WEB_MANUAL_PLAYER_IDS ?= 1

# デフォルトターゲット
help:
	@echo "利用可能なコマンド:"
	@echo "  make install      - 依存関係をインストール"
	@echo "  make dev-install  - 開発用依存関係をインストール"
	@echo "  make test         - テストを実行"
	@echo "  make test-cov     - カバレッジ付きでテストを実行"
	@echo "  make test-html    - HTMLカバレッジレポートを生成"
	@echo "  make clean        - 一時ファイルを削除"
	@echo "  make web-demo-db        - Web viewer 用の最小 SQLite DB を作成"
	@echo "  make web-demo-db-reset  - Web viewer 用 DB を再作成"
	@echo "  make web-backend        - Web viewer backend を起動"
	@echo "  make web-frontend-install - frontend 依存関係をインストール"
	@echo "  make web-frontend-test  - frontend テストを実行"
	@echo "  make web-frontend-build - frontend を build"
	@echo "  make web-frontend       - frontend dev server を起動"

# 依存関係のインストール
install:
	pip install -r requirements.txt

# 開発用依存関係のインストール
dev-install: install
	pip install pytest pytest-cov

# 基本的なテスト実行
test:
	pytest

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

web-demo-db:
	uv run python -m ai_rpg_world.presentation.web.demo_seed --database $(WEB_GAME_DB)

web-demo-db-reset:
	uv run python -m ai_rpg_world.presentation.web.demo_seed --database $(WEB_GAME_DB) --overwrite

web-backend:
	AI_RPG_WORLD_GAME_DB=$(WEB_GAME_DB) AI_RPG_WORLD_MANUAL_PLAYER_IDS=$(WEB_MANUAL_PLAYER_IDS) uv run python -m ai_rpg_world.presentation.web.server

web-frontend-install:
	cd frontend && npm install --cache .npm-cache

web-frontend-test:
	cd frontend && npm run test

web-frontend-build:
	cd frontend && npm run build

web-frontend:
	cd frontend && npm run dev
