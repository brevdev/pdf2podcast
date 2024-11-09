# Colors for better visibility
GREEN=\033[0;32m
RED=\033[0;31m
NC=\033[0m

# Test directories
TEST_DIR=tests
OUTPUTS_DIR=$(TEST_DIR)/outputs
SCHEMAS_DIR=$(TEST_DIR)/schemas
INPUTS_DIR=$(TEST_DIR)/inputs

# Ensure promptfoo is installed
ensure-promptfoo:
	@echo "$(GREEN)Checking npx installation...$(NC)"
	@if ! command -v npx >/dev/null 2>&1; then \
		echo "$(RED)Error: npx is not installed. Please install Node.js and npm first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Checking promptfoo installation...$(NC)"
	@if ! npx promptfoo@latest --version >/dev/null 2>&1; then \
		echo "$(GREEN)Installing promptfoo...$(NC)"; \
		npx promptfoo@latest --version >/dev/null 2>&1 || true; \
	fi

# Generate JSON schemas
generate-schemas:
	@echo "$(GREEN)Generating JSON schemas from Pydantic models...$(NC)"
	@python generate_schemas.py $(SCHEMAS_DIR)

# Setup test environment
setup-test: ensure-promptfoo
	@echo "$(GREEN)Setting up test environment...$(NC)"
	@mkdir -p $(INPUTS_DIR) $(OUTPUTS_DIR) $(SCHEMAS_DIR)
	@make generate-schemas

# Run end-to-end test
test-e2e: setup-test
	@echo "$(GREEN)Running end-to-end tests...$(NC)"
	npx promptfoo@latest eval --output $(OUTPUTS_DIR)/out.html

# Run original config
test-basic: ensure-promptfoo
	@echo "$(GREEN)Running basic promptfoo tests...$(NC)"
	npx promptfoo@latest eval -c promptfooconfig.yaml

# Clean test outputs
clean:
	@echo "$(GREEN)Cleaning test outputs...$(NC)"
	rm -rf $(TEST_DIR)

.PHONY: ensure-promptfoo generate-schemas setup-test test-e2e test-basic clean