.PHONY: setup run seed test lint clean

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt requirements-dev.txt
	cp -n .env.example .env || true

run:
	.venv/bin/python run.py

seed:
	.venv/bin/python seed.py

test:
	.venv/bin/python -m pytest tests/ -q

lint:
	.venv/bin/python -m pyflakes app/ run.py seed.py tests/

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
	rm -rf .pytest_cache
