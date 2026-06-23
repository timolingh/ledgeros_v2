.PHONY: down reset up test

down:
	docker compose down

reset:
	docker compose down -v

up:
	docker compose up -d db
	docker compose run --rm web python manage.py migrate
	docker compose up web

test:
	docker compose run --rm web pytest
