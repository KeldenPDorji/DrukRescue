# DrukRescue developer commands. Run `make help` to list them.
SHELL := /bin/bash
.DEFAULT_GOAL := help

SERVICES := $(sort $(filter-out _template,$(notdir $(wildcard services/*))))
CHARTS := $(filter-out drukrescue-lib,$(notdir $(wildcard deploy/charts/*)))
SERVICE_CHARTS := $(SERVICES) frontend
REGISTRY ?= ghcr.io/keldenpdorji
TAG ?= latest
ENV ?= dev
PYTHON ?= python3  # needs 3.12+; e.g. make venv PYTHON=python3.12
PY := .venv/bin/python

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F ':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- Python
.venv:
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e libs/common -r requirements-dev.txt $(addprefix -r services/,$(addsuffix /requirements.txt,$(SERVICES)))

.PHONY: venv
venv: .venv ## Create .venv with every service's dependencies

.PHONY: test
test: .venv ## Run all unit tests (each service separately: they each have an `app` package)
	@cd libs/common && ../../$(PY) -m pytest
	@set -e; for s in $(SERVICES) _template; do echo "== $$s"; (cd services/$$s && ../../$(PY) -m pytest); done

.PHONY: test-%
test-%: .venv ## Run one service's tests, e.g. make test-incident
	cd services/$* && ../../$(PY) -m pytest

.PHONY: lint
lint: .venv ## Lint Python with ruff
	.venv/bin/ruff check .

.PHONY: fmt
fmt: .venv ## Auto-fix lint issues (imports etc.)
	.venv/bin/ruff check --fix .

# ---------------------------------------------------------------- docker-compose (no Kubernetes)
.env:
	scripts/gen-env.sh

.PHONY: env
env: .env ## Create .env with random secrets for docker-compose

.PHONY: up
up: .env ## Build and start everything locally (frontend http://localhost:8080)
	docker compose up -d --build

.PHONY: down
down: ## Stop local stack (keeps data; `docker compose down -v` wipes it)
	docker compose down

.PHONY: logs
logs: ## Follow logs of all local services
	docker compose logs -f --tail=50

.PHONY: seed
seed: ## Seed demo responders, vehicles and logins (BASE=http://drukrescue.local for Kind)
	python3 scripts/seed.py $(if $(BASE),--base $(BASE))

.PHONY: smoke
smoke: ## End-to-end test of the demo flow against a running stack (BASE=... for Kind)
	python3 scripts/smoke_test.py $(if $(BASE),--base $(BASE))

# ---------------------------------------------------------------- images
.PHONY: images
images: ## Build all images as $(REGISTRY)/drukrescue-<svc>:$(TAG)
	@set -e; for s in $(SERVICES); do docker build -q --build-arg SERVICE=$$s -t $(REGISTRY)/drukrescue-$$s:$(TAG) . ; done
	docker build -q -t $(REGISTRY)/drukrescue-frontend:$(TAG) frontend

# ---------------------------------------------------------------- Helm
.PHONY: helm-deps
helm-deps: ## Vendor the library chart into each service chart
	@set -e; for c in $(SERVICE_CHARTS); do helm dependency build deploy/charts/$$c >/dev/null; done

.PHONY: helm-lint
helm-lint: helm-deps ## helm lint every chart
	@set -e; for c in $(CHARTS); do helm lint --quiet deploy/charts/$$c -f deploy/envs/$(ENV)/values.yaml >/dev/null || exit 1; done; \
	  helm lint --quiet deploy/argocd/apps >/dev/null; echo "all charts lint clean"

.PHONY: helm-template
helm-template: helm-deps ## Objective (a): render all 15 services + frontend from the library chart (ENV=dev|demo)
	@set -e; for c in $(SERVICE_CHARTS); do \
	  extra=""; [ -f deploy/envs/$(ENV)/services/$$c.yaml ] && extra="-f deploy/envs/$(ENV)/services/$$c.yaml"; \
	  helm template $$c deploy/charts/$$c -n drukrescue -f deploy/envs/$(ENV)/values.yaml $$extra; \
	done

# ---------------------------------------------------------------- Kind + ArgoCD
.PHONY: kind-up
kind-up: ## Create the Kind cluster, ingress, secrets, ArgoCD and the root app
	scripts/bootstrap-kind.sh

.PHONY: kind-load
kind-load: images ## Build images and load them into Kind (no registry needed)
	@set -e; for s in $(SERVICES) frontend; do kind load docker-image --name drukrescue $(REGISTRY)/drukrescue-$$s:$(TAG); done

.PHONY: kind-down
kind-down: ## Delete the Kind cluster
	kind delete cluster --name drukrescue

.PHONY: clean
clean: ## Remove caches and vendored chart dependencies
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache deploy/charts/*/charts deploy/charts/*/Chart.lock
