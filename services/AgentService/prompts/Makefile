# Colors for better visibility
GREEN=\033[0;32m
RED=\033[0;31m
NC=\033[0m

# Directory structure
CONFIG_DIR=configs
TEST_DIR=tests
OUTPUTS_DIR=$(TEST_DIR)/outputs
SCHEMAS_DIR=$(TEST_DIR)/schemas
INPUTS_DIR=$(TEST_DIR)/inputs

# Ensure promptfoo is installed
ensure-promptfoo:
	@echo "$(GREEN)Checking promptfoo installation...$(NC)"
	@if ! command -v promptfoo >/dev/null 2>&1; then \
		echo "$(RED)Error: promptfoo is not installed. Installing via brew...$(NC)"; \
		brew install promptfoo || { echo "$(RED)Failed to install promptfoo$(NC)"; exit 1; }; \
	fi

# Generate JSON schemas
generate-schemas:
	@echo "$(GREEN)Generating JSON schemas from Pydantic models...$(NC)"
	@python scripts/generate_schemas.py $(SCHEMAS_DIR)

# Setup test environment
setup-test: ensure-promptfoo
	@echo "$(GREEN)Setting up test environment...$(NC)"
	@mkdir -p $(INPUTS_DIR) $(OUTPUTS_DIR) $(SCHEMAS_DIR)
	@make generate-schemas

# Run all prompt tests
test-prompts: setup-test
	@echo "$(GREEN)Running all prompt tests...$(NC)"
	@cd $(CONFIG_DIR) && python ../scripts/run_tests.py

# Run up to a specific stage
test-upto: setup-test
	@if [ -z "$(stage)" ]; then \
		echo "$(RED)Error: Please specify a stage number with 'stage=N'$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Running prompt tests up to stage $(stage)...$(NC)"
	@cd $(CONFIG_DIR) && python ../scripts/run_tests.py --up-to $(stage)

# List all available test stages
test-list:
	@echo "$(GREEN)Listing available test stages...$(NC)"
	@python scripts/run_tests.py --list

# Clean test outputs
clean:
	@echo "$(GREEN)Cleaning test outputs...$(NC)"
	rm -rf $(TEST_DIR)

.PHONY: ensure-promptfoo generate-schemas setup-test test-prompts test-upto clean test-list