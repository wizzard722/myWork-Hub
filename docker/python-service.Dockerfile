# Bouwt één Python-service uit de uv-workspace.
# Voorbeeld:
#   docker build -f docker/python-service.Dockerfile \
#     --build-arg PACKAGE=mywork-core --build-arg MODULE=core.main .
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
ARG PACKAGE
RUN uv sync --frozen --no-dev --package "${PACKAGE}" --no-editable

FROM python:3.12-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 hub
COPY --from=build /opt/venv /opt/venv
# Map met het manifest van een app; voor de core blijft dit leeg.
ARG APP_DIR=docker/empty
COPY ${APP_DIR}/ /app/
WORKDIR /app
USER hub
ARG MODULE
ENV MODULE=${MODULE} ROOT_PATH=""
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn \"$MODULE:app\" --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --root-path \"$ROOT_PATH\""]
