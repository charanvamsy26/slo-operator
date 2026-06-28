# slo-operator developer Makefile
IMG ?= ghcr.io/charanvamsy26/slo-operator:latest
PY  ?= python3
VENV ?= .venv

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: venv
venv: ## Create venv and install dev dependencies
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install -U pip
	$(VENV)/bin/pip install -e ".[dev]"

.PHONY: lint
lint: ## Run ruff
	$(VENV)/bin/ruff check src tests

.PHONY: fmt
fmt: ## Auto-fix lint issues
	$(VENV)/bin/ruff check --fix src tests

.PHONY: test
test: ## Run the unit test suite
	$(VENV)/bin/python -m pytest

.PHONY: run
run: ## Run the operator locally against your current kube-context
	$(VENV)/bin/slo-operator

.PHONY: docker-build
docker-build: ## Build the container image
	docker build -t $(IMG) .

.PHONY: install-crd
install-crd: ## Install the CRD into the current cluster
	kubectl apply -f config/crd/servicelevelobjectives.yaml

.PHONY: deploy
deploy: ## Deploy the operator (requires Prometheus Operator CRDs)
	kubectl apply -k config/

.PHONY: undeploy
undeploy: ## Remove the operator from the cluster
	kubectl delete -k config/ --ignore-not-found

.PHONY: sample
sample: ## Apply the sample ServiceLevelObjective
	kubectl apply -f config/samples/servicelevelobjective.yaml
