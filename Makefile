.PHONY: dev worker redis db up down test test-integration test-e2e test-all lint fmt typecheck check eval bench seed gendata migrate migration clean

# ── Development ───────────────────────────────────────────────────────────────
dev:
	uvicorn app.main:app --reload --port 8000

worker:
	celery -A app.workers.celery_app worker --loglevel=info --concurrency=4

redis:
	docker run -d -p 6379:6379 redis:7-alpine

db:
	docker run -d -p 5432:5432 \
		-e POSTGRES_USER=postgres \
		-e POSTGRES_PASSWORD=postgres \
		-e POSTGRES_DB=autoinsight \
		postgres:16-alpine

up:
	docker-compose up -d

down:
	docker-compose down

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest tests/unit -v --tb=short

test-integration:
	pytest tests/integration -v --tb=short

test-e2e:
	pytest tests/e2e -v --tb=short

test-all:
	pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	ruff check app tests

fmt:
	black app tests
	ruff check --fix app tests

typecheck:
	mypy app --ignore-missing-imports

check: lint typecheck test

# ── Eval + bench ─────────────────────────────────────────────────────────────
eval:
	python eval/harness.py

bench:
	python bench/latency.py

# ── One-off scripts ──────────────────────────────────────────────────────────
seed:
	python scripts/seed_vectorstore.py

gendata:
	python scripts/generate_data.py

# ── DB migrations ─────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(msg)"

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
