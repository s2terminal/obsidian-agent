FROM docker.io/library/python:3.14.9-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# ベースイメージのキャッシュが古くても、OSのCA証明書は常に最新化する
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

FROM base AS dependencies

COPY pyproject.toml uv.lock ./

FROM dependencies AS development

RUN uv sync --frozen --no-install-project

COPY . .

CMD ["python", "main.py", "--help"]

FROM dependencies AS runtime

RUN uv sync --frozen --no-dev --no-install-project

COPY main.py ./
COPY scripts ./scripts

ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
