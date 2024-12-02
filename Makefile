# Env vars
include .env
export

# Detach var for CI
DETACH ?= 0

# Version for production deployment
VERSION := 4.2

# Docker registry and project
REGISTRY := nvcr.io/pfteb4cqjzrs/playground

# List of services to build
SERVICES := api-service agent-service pdf-service tts-service

# Required environment variables
REQUIRED_ENV_VARS := ELEVENLABS_API_KEY NIM_KEY MAX_CONCURRENT_REQUESTS

# Colors for terminal output
RED := \033[0;31m
GREEN := \033[0;32m
NC := \033[0m  # No Color

# Explicitly use bash
SHELL := /bin/bash

# List of all services used - pdf model services
CORE_SERVICES := redis minio api-service agent-service pdf-service tts-service jaeger

PDF_MODEL_SERVICES := redis pdf-api celery-worker

NVINGEST_URL := https://nv-ingest-8t8cjywa2.brevlab.com/v1

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

# UV environment setup target
uv:
	@echo "$(GREEN)Setting up UV environment...$(NC)"
	@bash setup.sh

# Create the minio data directory if it doesn't exist
create-minio-data-dir:
	@if [ ! -d "data/minio" ]; then \
		echo "$(GREEN)Creating data/minio directory...$(NC)"; \
		mkdir -p data/minio; \
	fi

# CI target that will use a remote hosted NV-Ingest service
ci: check_env create-minio-data-dir
	docker compose down $(CORE_SERVICES)
	@echo "$(GREEN)Starting CI environment...$(NC)"
	@if [ "$(DETACH)" = "1" ]; then \
		MODEL_API_URL=$(NVINGEST_URL) docker compose -f docker-compose.yaml --env-file .env up $(CORE_SERVICES) --build -d; \
	else \
		MODEL_API_URL=$(NVINGEST_URL) docker compose -f docker-compose.yaml --env-file .env up $(CORE_SERVICES) --build; \
	fi

# Development target that does not locally run and build docling. Make sure to set the MODEL_API_URL environment variable to the correct URL.
dev: check_env create-minio-data-dir
	docker compose down $(CORE_SERVICES)
	@echo "$(GREEN)Starting development environment...$(NC)"
	@if [ "$(DETACH)" = "1" ]; then \
		docker compose -f docker-compose.yaml --env-file .env up $(CORE_SERVICES) --build -d; \
	else \
		docker compose -f docker-compose.yaml --env-file .env up $(CORE_SERVICES) --build; \
	fi

# Development target to build the pdf model service (docling) for local development
model-dev:
	docker compose down $(PDF_MODEL_SERVICES)
	@echo "$(GREEN)Starting development environment...$(NC)"
	docker compose up $(PDF_MODEL_SERVICES) --build

# Production target to pull pdf model service (docling) in production. Use this if you want to host the pdf model service on a separate machine.
model-prod:
	docker compose -f docker-compose-remote.yaml down $(PDF_MODEL_SERVICES)
	@echo "$(GREEN)Starting production environment with version $(VERSION)...$(NC)"
	VERSION=$(VERSION) docker compose -f docker-compose-remote.yaml up $(PDF_MODEL_SERVICES)

# Development target that will run all services including the pdf model service (docling) locally
all-services: check_env create-minio-data-dir
	docker compose down
	@echo "$(GREEN)Starting development environment all-services...$(NC)"
	@if [ "$(DETACH)" = "1" ]; then \
		docker compose -f docker-compose.yaml --env-file .env up --build -d; \
	else \
		docker compose -f docker-compose.yaml --env-file .env up --build; \
	fi

# Production target that will pull core services. This is meant to used in conjunction when you run make model-prod on a separate machine
prod: check_env create-minio-data-dir
	docker compose down $(CORE_SERVICES)
	@echo "$(GREEN)Starting production environment with version $(VERSION)...$(NC)"
	VERSION=$(VERSION) docker compose -f docker-compose-remote.yaml --env-file .env up $(CORE_SERVICES)

# Version bump (minor) and release target
version-bump:
	@echo "Current version: $(VERSION)"
	@new_version=$$(echo $(VERSION) | awk -F. '{$$NF = $$NF + 1;} 1' | sed 's/ /./g'); \
	sed -i.bak "s/VERSION := $(VERSION)/VERSION := $$new_version/" Makefile; \
	rm Makefile.bak; \
	echo "$(GREEN)Version bumped to: $$new_version$(NC)"; \
	git add Makefile; \
	git commit -m "chore: bump version to $$new_version"; \
	git tag -a "v$$new_version" -m "Release v$$new_version"; \
	git push origin main; \
	git push origin "v$$new_version"

# Version bump (major) and release target
version-bump-major:
	@echo "Current version: $(VERSION)"
	@new_version=$$(echo $(VERSION) | awk -F. '{$$1 = $$1 + 1; $$2 = 0;} 1' | sed 's/ /./g'); \
	sed -i.bak "s/VERSION := $(VERSION)/VERSION := $$new_version/" Makefile; \
	rm Makefile.bak; \
	echo "$(GREEN)Version bumped to: $$new_version$(NC)"; \
	git add Makefile; \
	git commit -m "chore: bump major version to $$new_version"; \
	git tag -a "v$$new_version" -m "Release v$$new_version"; \
	git push origin main; \
	git push origin "v$$new_version"

# Clean up containers and volumes
clean:
	docker compose -f docker-compose.yaml down -v

lint:
	ruff check

format:
	ruff format

ruff: lint format

.PHONY: check_env dev clean ruff prod version-bump version-bump-major uv model-prod model-dev all-services create-minio-data-dir