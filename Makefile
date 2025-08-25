# Makefile
.PHONY: format check ci install-dev clean

# Format code in-place
format:
	isort .
	black .

# Fail if formatting is needed (good for CI)
check:
	isort . --check-only
	black . --check

# Convenience target for CI systems
ci: check

# Install required dev tools
install-dev:
	python -m pip install -U pip
	pip install black isort

# Optional: remove caches
clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache build dist *.egg-info
