.PHONY: setup dev db migrate test check e2e docker benchmark
setup:
	uv sync --directory apps/backend --frozen
	cd apps/frontend && npm ci

db:
	docker compose up -d db --wait

migrate:
	uv run --directory apps/backend alembic upgrade head

dev:
	bash scripts/dev.sh

test:
	uv run --directory apps/backend pytest -q
	cd apps/frontend && npm test

check:
	uv run --directory apps/backend ruff check app tests
	uv run --directory apps/backend mypy app
	cd apps/frontend && npm run build

e2e:
	cd apps/frontend && npm run test:e2e

docker:
	docker compose up --build -d --wait

benchmark:
	uv run --directory apps/backend python -m app.experiments.cli --scenario ../../scenarios/small.json --config ../../scenarios/benchmarks/A-open-space.json --output ../../docs/experiments/benchmark-A.json
