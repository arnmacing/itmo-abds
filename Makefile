include .env.local

COMPOSE = docker compose --env-file .env.local

.PHONY: run rund services stop clean gen load setup teardown
.DEFAULT_GOAL = run

# Runs all services in detached mode.
run:
	$(COMPOSE) up -d --build

# Runs all services without detached mode (for debugging).
rund:
	$(COMPOSE) up --build

# Shows all service statuses.
services:
	$(COMPOSE) ps

# Stops all running services.
stop:
	$(COMPOSE) down

# Cleans up all resources including volumes.
clean:
	$(COMPOSE) down -v

# Generates datasets into data/.
gen:
	python3 gen/generate.py

# Loads CSV from data/ into ClickHouse.
load:
	./scripts/load.sh

# Creates the schema, generates and loads datasets.
setup:
	$(COMPOSE) exec -T clickhouse clickhouse-client --password '$(CLICKHOUSE_PASSWORD)' --queries-file /dev/stdin < sql/schema.sql
	$(MAKE) gen load

# Drops all tables and data.
teardown:
	$(COMPOSE) exec -T clickhouse clickhouse-client --password '$(CLICKHOUSE_PASSWORD)' --queries-file /dev/stdin < sql/teardown.sql
