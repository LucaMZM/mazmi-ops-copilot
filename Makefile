.PHONY: up down logs backend-test frontend-check
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
