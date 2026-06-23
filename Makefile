.PHONY: help up down reset build test check shell migrate

help:
	@printf '%s\n' \
		'LedgerOS container workflow:' \
		'  make up       - start LedgerOS with db, run migrations, then bring web up' \
		'  make down     - stop the LedgerOS stack' \
		'  make reset    - stop the LedgerOS stack and remove volumes' \
		'  make build    - build Docker images' \
		'  make migrate  - run Django migrations in Docker' \
		'  make test     - run the Django test suite in Docker only' \
		'  make check    - run Django checks in Docker only' \
		'  make shell    - open a Django shell in the web container'

up:
	docker compose -f docker-compose.yml up -d db
	docker compose -f docker-compose.yml run --rm web python manage.py migrate
	docker compose -f docker-compose.yml up web

down:
	docker compose -f docker-compose.yml down --remove-orphans

reset:
	docker compose -f docker-compose.yml down -v --remove-orphans

build:
	docker compose -f docker-compose.yml build

test:
	docker compose -f docker-compose.yml run --rm web pytest

check:
	docker compose -f docker-compose.yml run --rm web python manage.py check
	docker compose -f docker-compose.yml run --rm web python manage.py makemigrations --check --dry-run

shell:
	docker compose -f docker-compose.yml run --rm web python manage.py shell

migrate:
	docker compose -f docker-compose.yml run --rm web python manage.py migrate
