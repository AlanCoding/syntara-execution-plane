.PHONY: install test test-integration lint format typecheck generate api-spec generate-schemas migrate image secrets certs setup compose-up compose-down

install:
	uv sync --locked --all-groups

test:
	uv run pytest

test-integration:
	uv run pytest tests/integration -m integration -v

lint:
	uv run ruff check src tests

format:
	uv run ruff format --check src tests

typecheck:
	uv run mypy --strict src

generate: generate-schemas

api-spec:
	uv run python tools/export_openapi.py

generate-schemas: api-spec
	uvx --from datamodel-code-generator datamodel-codegen \
		--input openapi.yaml \
		--input-file-type openapi \
		--output src/execution_plane/api/generated.py \
		--output-model-type pydantic_v2.BaseModel \
		--use-annotated \
		--use-standard-collections \
		--target-python-version 3.12
	sed -i '/^#.*timestamp:/d' src/execution_plane/api/generated.py
	sed -i 's|^#   filename:  openapi.yaml$$|#   filename:  openapi.yaml\n#\n# DO NOT EDIT — regenerate with: make generate|' src/execution_plane/api/generated.py

migrate:
	uv run alembic -c alembic.ini upgrade head

image:
	podman build -f Containerfile -t localhost/execution-plane:dev .

secrets:
	./tools/generate_secrets.sh

certs:
	uv run python tools/generate_certs.py

setup: install secrets certs

compose-up: setup
	uvx podman-compose -f compose.yaml up --build

compose-down:
	uvx podman-compose -f compose.yaml down
