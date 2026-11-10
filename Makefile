.PHONY: setup migrate backend frontend check-local up down logs backend-test frontend-check

# Ejecución nativa (recomendada): PostgreSQL con pgvector y Ollama en tu equipo.
setup:
	python3.13 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.lock
	test -e .env || cp .env.example .env
	cd frontend && npm ci

migrate:
	cd backend && python -m app.migrate

backend:
	cd backend && python -m app.migrate && uvicorn app.main:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

# Comprueba los modelos instalados en Ollama (no descarga nada).
check-local:
	cd backend && python -m app.check_local

# Docker Compose es opcional: Ollama sigue ejecutándose en el equipo anfitrión.
up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

backend-test:
	cd backend && python -m pytest && ruff check .

frontend-check:
	cd frontend && npm run typecheck && npm run lint && npm test && npm run build
