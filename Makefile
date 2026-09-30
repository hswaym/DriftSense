.PHONY: test lint clean help

help:
	@echo "Available commands:"
	@echo "  make test      Run unit and invariant enforcement tests"
	@echo "  make lint      Run ruff check"
	@echo "  make clean     Clean temporary build, cache, and pytest files"

test:
	pytest tests/ -v

lint:
	ruff check .

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
