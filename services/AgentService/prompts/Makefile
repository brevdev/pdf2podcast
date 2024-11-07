promptfoo:
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
	@echo "$(GREEN)Running promptfoo in AgentService prompts directory...$(NC)"
	npx promptfoo@latest eval

.PHONY: promptfoo