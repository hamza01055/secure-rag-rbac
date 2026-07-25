.PHONY: help up down logs seed test verify eval lint console fmt clean

help:
	@echo "up       start the full stack"
	@echo "seed     roles, users, and the classified test corpus"
	@echo "test     unit + integration tests"
	@echo "verify   adversarial permission tests (release blocker)"
	@echo "eval     retrieval quality + permission leak rate"
	@echo "lint     architectural boundary check"
	@echo "console  serve the developer console on :5500"

up:
	docker compose up -d --build
	@echo "api  http://localhost:8000/docs"
	@echo "web  http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f api worker

seed:
	docker compose exec api python -m seeds.seed

test:
	cd backend && python -m pytest -q

verify:
	python scripts/verify_rbac.py --canary "Project Nightingale severance"

eval:
	python scripts/eval_retrieval.py --evalset scripts/evalset.json

lint:
	python scripts/lint_boundaries.py
	cd backend && ruff check app tests

console:
	@echo "open http://localhost:5500/dev-console.html"
	cd devtools && python -m http.server 5500

fmt:
	cd backend && ruff format app tests

clean:
	docker compose down -v
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
