# Required environment variables
REQUIRED_ENV_VARS := ELEVENLABS_API_KEY NIM_KEY MAX_CONCURRENT_REQUESTS

# Colors for terminal output
RED := \033[0;31m
GREEN := \033[0;32m
NC := \033[0m  # No Color

# Explicitly use bash
SHELL := /bin/bash

# Check if environment variables are set
check_env:
	@for var in $(REQUIRED_ENV_VARS); do \
		if [ -z "$$(eval echo "\$$$$var")" ]; then \
			echo "$(RED)Error: $$var is not set$(NC)"; \
			echo "Please set required environment variables:"; \
			echo "  export $$var=<value>"; \
			exit 1; \
		else \
			echo "$(GREEN)✓ $$var is set$(NC)"; \
		fi \
	done

# Development target
dev: check_env
	@echo "$(GREEN)Starting development environment...$(NC)"
	docker compose -f docker-compose.yaml up --build

# Clean up containers and volumes
clean:
	docker compose -f docker-compose.yaml down -v

lint:
	ruff check

format: 
	ruff format

ruff: lint format

.PHONY: check_env dev clean ruff