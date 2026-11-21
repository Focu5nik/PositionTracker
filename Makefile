DOCKER ?= docker

.PHONY: up down logs lint test migrate smoke

up:
	$(DOCKER) compose up --build --wait

down:
	$(DOCKER) compose down

logs:
	$(DOCKER) compose logs --tail=100

lint:
	$(DOCKER) compose run --build --rm -T --no-deps monolith ruff check apps tests
	$(DOCKER) compose run --rm -T --no-deps monolith mypy

test:
	$(DOCKER) compose run --build --rm -T --no-deps monolith python -m pytest

migrate:
	$(DOCKER) compose exec -T monolith python -m apps.monolith.manage migrate
	$(DOCKER) compose exec -T tracker python -m alembic upgrade head

smoke:
	$(DOCKER) compose exec -T -e RUN_COMPOSE_TESTS=1 -e DJANGO_SETTINGS_MODULE=apps.monolith.config.settings monolith python -m pytest tests/test_compose.py
	$(DOCKER) compose exec -T -e RUN_COMPOSE_TESTS=1 tracker python -m pytest tests/test_compose.py
