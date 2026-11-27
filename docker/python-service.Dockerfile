# Bouwt één Python-service (core of app) op gehardende Chainguard-images.
#
#   docker build -f docker/python-service.Dockerfile \
#     --build-arg PACKAGE=mywork-core --build-arg MODULE=core.main -t mywork-hub-core .
#
# Bouwfase: python:latest-dev (met shell en pip). Draaifase: python:latest — geen shell,
# geen package manager, draait als niet-root (uid 65532). De basisimages zijn via
# build-args te vervangen, bijv. door een vastgepinde digest of Docker Hardened Images.
ARG PYTHON_BUILD_IMAGE=cgr.dev/chainguard/python:latest-dev
ARG PYTHON_IMAGE=cgr.dev/chainguard/python:latest

FROM ${PYTHON_BUILD_IMAGE} AS build
USER root
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --no-cache-dir "uv>=0.11,<0.12"
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
ARG PACKAGE
RUN uv sync --frozen --no-dev --no-editable --package "${PACKAGE}" --python /usr/bin/python3

FROM ${PYTHON_IMAGE}
COPY --from=build /opt/venv /opt/venv
# Map met het manifest van een app; voor de core blijft dit leeg.
ARG APP_DIR=docker/empty
COPY ${APP_DIR}/ /app/
WORKDIR /app
ARG MODULE
ENV MODULE=${MODULE} ROOT_PATH="" PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
USER 65532
EXPOSE 8000
ENTRYPOINT ["/opt/venv/bin/python", "-m", "mywork_sdk.serve"]
