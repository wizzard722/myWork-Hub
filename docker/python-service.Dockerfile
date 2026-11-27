# Bouwt één Python-service (core, assistent of app) op Alpine Linux, gehardend.
#
#   docker build -f docker/python-service.Dockerfile \
#     --build-arg PACKAGE=mywork-core --build-arg MODULE=core.main -t mywork-hub-core .
#
# Gehardend: in de draaifase geen package manager (apk), geen setuid-bestanden en geen
# shell; draait als niet-root (uid 65532). Basisimage met vaste versie; via build-arg
# te vervangen (bijv. door een digest: python:3.13-alpine3.22@sha256:...).
# Achter een proxy met eigen CA: --secret id=ca_bundle,src=ca.crt (komt niet in het image).
ARG PYTHON_IMAGE=python:3.13-alpine3.22

FROM ${PYTHON_IMAGE} AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv PIP_DISABLE_PIP_VERSION_CHECK=1
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/ca_bundle PIP_CERT=/run/secrets/ca_bundle NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    pip install --no-cache-dir "uv>=0.11,<0.12"
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
COPY apps ./apps
ARG PACKAGE
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/ca_bundle PIP_CERT=/run/secrets/ca_bundle NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    uv sync --frozen --no-dev --no-editable --package "${PACKAGE}" --python /usr/local/bin/python3

FROM ${PYTHON_IMAGE}
COPY --from=build /opt/venv /opt/venv
# Map met het manifest van een app; voor core en assistent blijft dit leeg.
ARG APP_DIR=docker/empty
COPY ${APP_DIR}/ /app/
# Harden: updates, pip/setuptools weg, setuid-bits weg, package manager weg en als
# allerlaatste de shell (busybox). Hierna is geen RUN meer mogelijk.
# Beveiligingsupdates van Alpine meenemen (standaard aan).
ARG APK_UPGRADE=true
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/ca_bundle PIP_CERT=/run/secrets/ca_bundle NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    if [ "$APK_UPGRADE" = "true" ]; then apk upgrade --no-cache; fi \
 && rm -rf /usr/local/lib/python3*/site-packages/pip* /usr/local/bin/pip* \
 && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
 && rm -rf /sbin/apk /etc/apk /lib/apk /usr/share/apk /var/cache/apk /root/.cache \
 && rm -f /bin/busybox /bin/sh
WORKDIR /app
ARG MODULE
ENV MODULE=${MODULE} ROOT_PATH="" PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
USER 65532:65532
EXPOSE 8000
ENTRYPOINT ["/opt/venv/bin/python", "-m", "mywork_sdk.serve"]
