.DEFAULT_GOAL := help

COMPOSE := docker compose -f docker-compose.yaml -f docker-compose.override.yaml

.PHONY: help up stop down build logs ps config test

help:
	@echo "up / stop / down / build / logs / ps / config / test"

test:
	uv run pytest

up:
	$(COMPOSE) up -d --build

stop:
	$(COMPOSE) stop

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs --follow --tail=100

ps:
	$(COMPOSE) ps -a

config:
	$(COMPOSE) config --quiet
