SHELL := bash

.SHELLFLAGS := -eu -o pipefail -c

.PHONY: unit \
		harness-start \
		harness-stop \
		integration \
		tests \
		integration-docker \
		image-test \
		image-minikube \
		clean

# Runs the unit tests locally.
unit:
	poetry run pytest -m "not deluge_integration and not codex_integration"

deluge-harness-start:
	docker compose -f docker-compose-deluge.local.yaml up

codex-harness-start:
	docker compose -f docker-compose-codex.local.yaml up

deluge-harness-stop:
	docker compose -f docker-compose-deluge.local.yaml down --volumes --remove-orphans

codex-harness-stop:
	docker compose -f docker-compose-codex.local.yaml down --volumes --remove-orphans

# Runs the integration tests locally. This requires the integration harness to be running.
deluge-integration:
	echo "NOTE: Make sure to have started the Deluge integration harness or this will not work"
	poetry run pytest -m "deluge_integration"

codex-integration:
	echo "NOTE: Make sure to have started the Codex integration harness or this will not work"
	poetry run pytest -m "codex_integration"

image-test:
	docker build -t bittorrent-benchmarks:test -f ./docker/bittorrent-benchmarks.Dockerfile .

export CODEX_REPO_PATH

codex-image-minikube:
	@if [ -z "$(CODEX_REPO_PATH)" ]; then \
		echo "Error: CODEX_REPO_PATH environment variable is not set"; \
		exit 1; \
	fi
	eval $$(minikube docker-env) && \
	cd ${CODEX_REPO_PATH} && \
	docker build -t logos-storage-nim:minikube -f ./docker/codex.Dockerfile .

harness-image-minikube:
	eval $$(minikube docker-env) && \
	docker build -t bittorrent-benchmarks:minikube \
		--build-arg BUILD_TYPE="release" \
		-f ./docker/bittorrent-benchmarks.Dockerfile . && \
	docker build -t bittorrent-benchmarks-workflows:minikube \
		-f ./docker/bittorrent-benchmarks-workflows.Dockerfile .

# Runs the integration tests in a docker container.
deluge-integration-docker: image-test
	docker compose -f docker-compose-deluge.local.yaml -f docker-compose-deluge.ci.yaml down --volumes --remove-orphans
	docker compose -f docker-compose-deluge.local.yaml -f docker-compose-deluge.ci.yaml up \
		--abort-on-container-exit --exit-code-from test-runner

codex-integration-docker: image-test
	docker compose -f docker-compose-codex.local.yaml -f docker-compose-codex.ci.yaml down --volumes --remove-orphans
	docker compose -f docker-compose-codex.local.yaml -f docker-compose-codex.ci.yaml up \
		--abort-on-container-exit --exit-code-from test-runner
clean:
	docker compose -f docker-compose.local.yaml -f docker-compose.ci.yaml down --volumes --rmi all --remove-orphans
