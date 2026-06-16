PY ?= .venv313/bin/python
PIP ?= .venv313/bin/pip
ALEMBIC ?= $(PY) -m alembic

.PHONY: venv install test run demo clean migrate migration migrate-down migrate-history \
        desktop desktop-install desktop-build

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

tools-thy:           ## Build the THY/ULD-line accelerator tools (cargo dim / damage / apron energy)
	docker build -t glowsky-tool-cargo-dimensioning:0.1.0 examples/tools/cargo_dimensioning
	docker build -t glowsky-tool-damage-detect:0.1.0 examples/tools/damage_detect
	docker build -t glowsky-tool-apron-energy:0.1.0 examples/tools/apron_energy

up:                  ## Build + run the full stack (redis + api + worker)
	docker compose up --build

down:                ## Stop the stack
	docker compose down

up-docking:          ## Build + run the stack with real Vina/OpenBabel docking (amd64; emulated on Apple Silicon)
	docker compose -f docker-compose.yml -f docker-compose.docking.yml up --build

migrate:             ## Apply all pending migrations (alembic upgrade head)
	$(ALEMBIC) upgrade head

migration:           ## Autogenerate a migration from model changes: make migration m="add foo"
	$(ALEMBIC) revision --autogenerate -m "$(m)"

migrate-down:        ## Roll back the most recent migration
	$(ALEMBIC) downgrade -1

migrate-history:     ## Show migration history + current revision
	$(ALEMBIC) history --verbose && $(ALEMBIC) current

desktop-install:     ## Install the desktop app's JS deps (Tauri + React + Vite)
	cd apps/desktop && pnpm install

desktop:             ## Run the desktop app (needs `make run` for the backend)
	cd apps/desktop && pnpm desktop

desktop-build:       ## Build a native desktop installer (.dmg/.msi/.deb)
	cd apps/desktop && pnpm desktop:build

demo:                ## Run a sample design loop and print the result
	$(PY) -m scripts.demo

clean:
	rm -f glowsky.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
