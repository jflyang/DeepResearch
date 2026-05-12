.PHONY: install api ui test lint fmt clean

install:
	pip install -e ".[dev]"

api:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

ui:
	streamlit run ui/streamlit_app.py --server.port 8501

test:
	pytest -v --cov=services --cov=providers --cov=utils

lint:
	ruff check .

fmt:
	ruff format .
	ruff check --fix .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache *.egg-info
