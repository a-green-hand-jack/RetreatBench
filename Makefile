.PHONY: install test coverage schemas schemas-check validate-examples clean

install:
	python -m pip install -e '.[dev]'

test:
	pytest

coverage:
	pytest --cov=retreatbench --cov-report=term-missing

schemas:
	python scripts/export_schemas.py

schemas-check:
	python scripts/export_schemas.py --check

validate-examples:
	retreatbench validate examples/goal_contract.example.json
	retreatbench validate examples/behavior_result.self_recoverable.json
	retreatbench classify examples/decision_context.self_recoverable.json >/dev/null
	retreatbench aggregate examples/behavior_results.example.jsonl >/dev/null

clean:
	rm -rf .pytest_cache .coverage htmlcov build dist src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
