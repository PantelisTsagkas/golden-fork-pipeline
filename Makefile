# =============================================================================
# Makefile — Golden Fork Pipeline
# Usage: make <target>
# =============================================================================

.PHONY: install test coverage generate package clean

# Install all dependencies (including dev) via uv
install:
	uv sync --group dev

# Run the full test suite
test:
	uv run pytest tests/

# Run tests with coverage report
coverage:
	uv run pytest tests/ --cov=lambda --cov-report=term-missing

# Generate synthetic orders CSV (500 rows, reproducible)
generate:
	uv run python generate_orders.py --rows 500 --seed 42

# Package Lambda code into a zip for manual upload or inspection
package:
	mkdir -p terraform/builds
	cd lambda && zip -r ../terraform/builds/validator.zip validator/ shared/ && cd ..
	cd lambda && zip -r ../terraform/builds/loader.zip loader/ shared/ && cd ..
	cd lambda && zip -r ../terraform/builds/alerter.zip alerter/ && cd ..
	@echo "Lambda packages → terraform/builds/"

# Remove generated artifacts
clean:
	rm -rf .venv terraform/builds orders.csv
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
