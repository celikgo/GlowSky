PY ?= .venv313/bin/python
PIP ?= .venv313/bin/pip

.PHONY: venv install test run demo clean

venv:                ## Create the Python 3.13 virtualenv (RDKit-compatible)
	/opt/homebrew/bin/python3.13 -m venv .venv313

install:             ## Install the package + dev deps (editable)
	$(PIP) install -e ".[dev]"

test:                ## Run the test suite
	$(PY) -m pytest -q

run:                 ## Start the API (offline mock LLM by default)
	$(PY) -m uvicorn apps.api.main:app --reload --port 8000

worker:              ## Start a Celery worker for the slow path (needs GLOWSKY_REDIS_URL)
	$(PY) -m celery -A services.tools.queue.celery_app worker --loglevel=info

redis:               ## Start a local Redis for the slow path (Docker)
	docker run --rm -p 6379:6379 redis:7-alpine

tool-example:        ## Build the example container tool image
	docker build -t glowsky-tool-molecular-formula:0.1.0 examples/tools/molecular_formula

tool-admet:          ## Build the real ADMET-AI container tool (large: torch; ~minutes)
	docker build -t glowsky-tool-admet-ai:0.1.0 examples/tools/admet_ai

up:                  ## Build + run the full stack (redis + api + worker)
	docker compose up --build

down:                ## Stop the stack
	docker compose down

demo:                ## Run a sample design loop and print the result
	$(PY) -m scripts.demo

clean:
	rm -f glowsky.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
