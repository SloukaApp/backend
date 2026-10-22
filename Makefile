.DEFAULT_GOAL := help

COMPOSE_DEV := docker compose -f docker-compose.yaml -f docker-compose.override.yaml
COMPOSE_PROD := docker compose -f docker-compose.yaml -f docker-compose.prod.yaml

.PHONY: help dev-up dev-stop dev-down dev-build dev-logs dev-ps dev-config \
        prod-up prod-stop prod-down prod-build prod-logs prod-ps prod-config

help:
	@echo "make dev-up / prod-up       Собрать и запустить окружение в фоне"
	@echo "make dev-stop / prod-stop   Остановить контейнеры"
	@echo "make dev-down / prod-down   Остановить и удалить контейнеры и сеть"
	@echo "make dev-build / prod-build Собрать образы"
	@echo "make dev-logs / prod-logs   Следить за логами"
	@echo "make dev-ps / prod-ps       Показать состояние контейнеров"
	@echo "make dev-config / prod-config Проверить конфигурацию без вывода секретов"

dev-up:
	$(COMPOSE_DEV) up -d --build

prod-up:
	$(COMPOSE_PROD) up -d --build

dev-stop:
	$(COMPOSE_DEV) stop

prod-stop:
	$(COMPOSE_PROD) stop

dev-down:
	$(COMPOSE_DEV) down

prod-down:
	$(COMPOSE_PROD) down

dev-build:
	$(COMPOSE_DEV) build

prod-build:
	$(COMPOSE_PROD) build

dev-logs:
	$(COMPOSE_DEV) logs --follow --tail=100

prod-logs:
	$(COMPOSE_PROD) logs --follow --tail=100

dev-ps:
	$(COMPOSE_DEV) ps -a

prod-ps:
	$(COMPOSE_PROD) ps -a

dev-config:
	$(COMPOSE_DEV) config --quiet

prod-config:
	$(COMPOSE_PROD) config --quiet
