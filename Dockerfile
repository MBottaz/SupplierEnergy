# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

FROM ${PYTHON_IMAGE} AS builder

# uv is used only while building the locked virtual environment.
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime

ARG DB_GROUP_GID=1000
ARG ETL_UID=1001
ARG MCP_UID=1002

RUN groupadd --gid "${DB_GROUP_GID}" offerte-db \
    && useradd --no-log-init --uid "${ETL_UID}" --gid offerte-db --no-create-home --shell /usr/sbin/nologin offerte-etl \
    && useradd --no-log-init --uid "${MCP_UID}" --gid offerte-db --no-create-home --shell /usr/sbin/nologin offerte-mcp \
    && install -d -o offerte-etl -g offerte-db -m 0750 /var/lib/offerte/db \
    && install -d -o offerte-etl -g offerte-db -m 0700 /var/lib/offerte/raw \
    && install -d -o offerte-etl -g offerte-db -m 0700 /var/lib/offerte/locks

COPY --from=builder /build/.venv /opt/offerte/.venv
COPY etl /opt/offerte/etl
COPY offerte /opt/offerte/offerte

ENV PATH="/opt/offerte/.venv/bin:${PATH}" \
    PYTHONPATH=/opt/offerte \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/offerte

# The default is MCP. Docker Compose or `docker run ... -m etl ...` can select
# the batch command without rebuilding the image; both users are in the image.
USER offerte-mcp
ENTRYPOINT ["python"]
CMD ["-m", "offerte.mcp"]
