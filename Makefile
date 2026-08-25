SHELL := /bin/bash
PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
KIND := .tools/bin/kind
HELM := .tools/bin/helm
KIND_NODE_IMAGE := kindest/node:v1.34.0@sha256:7416a61b42b1662ca6ca89f02028ac133a309a2a30ba309614e8ec94d976dc5a
OTEL_DEMO_CHART_VERSION := 0.41.0
CHAOS_MESH_CHART_VERSION := 2.8.4
GROUND_TRUTH_DIR ?= $(abspath ../.rootlens-ground-truth)
COMPOSE := ROOTLENS_PROJECT_DIR="$(CURDIR)" docker compose \
	--project-name rootlens \
	--env-file vendor/opentelemetry-demo/.env \
	--env-file .env.compose \
	-f vendor/opentelemetry-demo/compose.yaml \
	-f compose.yaml

.PHONY: bootstrap chaos-smoke chaos-validate check compose-config down format gateway-smoke k8s-core-up k8s-down k8s-smoke k8s-tools k8s-up lint migrate smoke test topology-smoke typecheck up

bootstrap:
	git submodule update --init --recursive
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install --constraint requirements.lock -e '.[dev]'

format:
	$(VENV_PYTHON) -m ruff format .
	$(VENV_PYTHON) -m ruff check --fix .

lint:
	$(VENV_PYTHON) -m ruff format --check .
	$(VENV_PYTHON) -m ruff check .

typecheck:
	$(VENV_PYTHON) -m mypy

test:
	ROOTLENS_TELEMETRY_ENABLED=false $(VENV_PYTHON) -m pytest

check: lint typecheck test compose-config

compose-config:
	$(COMPOSE) config --quiet

up:
	git submodule update --init --recursive
	$(COMPOSE) build rootlens-api
	$(COMPOSE) up --detach --no-build --wait
	$(COMPOSE) run --rm rootlens-api alembic upgrade head
	$(VENV_PYTHON) scripts/verify_stack.py

down:
	$(COMPOSE) down --remove-orphans

migrate:
	$(COMPOSE) run --rm rootlens-api alembic upgrade head

smoke:
	$(VENV_PYTHON) scripts/verify_stack.py

gateway-smoke:
	$(VENV_PYTHON) scripts/verify_gateway.py

topology-smoke:
	$(VENV_PYTHON) scripts/verify_topology.py

k8s-tools:
	bash scripts/bootstrap_k8s_tools.sh

k8s-core-up:
	$(COMPOSE) down --remove-orphans
	$(COMPOSE) build rootlens-api
	$(COMPOSE) up --detach --no-build --wait rootlens-db prometheus tempo loki grafana otel-collector rootlens-api
	$(COMPOSE) run --rm rootlens-api alembic upgrade head

k8s-up: k8s-tools k8s-core-up
	@if ! $(KIND) get clusters | rg --quiet '^rootlens$$'; then \
		$(KIND) create cluster --image '$(KIND_NODE_IMAGE)' --config infrastructure/kubernetes/kind-config.yaml; \
	fi
	kubectl --context kind-rootlens apply --filename infrastructure/kubernetes/namespaces.yaml
	$(HELM) repo add chaos-mesh https://charts.chaos-mesh.org --force-update
	$(HELM) repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts --force-update
	$(HELM) repo update
	$(HELM) upgrade --install chaos-mesh chaos-mesh/chaos-mesh --version $(CHAOS_MESH_CHART_VERSION) --namespace chaos-mesh --create-namespace --values infrastructure/kubernetes/chaos-mesh-values.yaml --wait --timeout 10m
	$(HELM) upgrade --install otel-demo open-telemetry/opentelemetry-demo --version $(OTEL_DEMO_CHART_VERSION) --namespace otel-demo --values infrastructure/kubernetes/otel-demo-values.yaml --wait --timeout 15m
	$(VENV_PYTHON) scripts/verify_kubernetes.py

k8s-smoke:
	$(VENV_PYTHON) scripts/verify_kubernetes.py

chaos-validate:
	@for fault in pod_kill cpu_stress network_latency packet_loss http_delay; do \
		$(VENV_PYTHON) -m experiment_controller.cli validate --fault "$$fault" --duration 10; \
	done

chaos-smoke:
	$(VENV_PYTHON) -m experiment_controller.cli run --fault pod_kill --duration 10 --ground-truth-dir '$(GROUND_TRUTH_DIR)' --confirm
	PYTHONPATH='$(CURDIR)' $(VENV_PYTHON) scripts/verify_ground_truth.py '$(GROUND_TRUTH_DIR)'

k8s-down:
	$(KIND) delete cluster --name rootlens
