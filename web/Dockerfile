# Web-schil: bouwen met Node (Alpine), serveren met nginx (Alpine), gehardend:
# geen shell, geen apk, niet-root (uid 65532).
ARG NODE_BUILD_IMAGE=node:22-alpine3.22
ARG NGINX_IMAGE=nginx:1.28-alpine

FROM ${NODE_BUILD_IMAGE} AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/ca_bundle PIP_CERT=/run/secrets/ca_bundle NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM ${NGINX_IMAGE}
COPY nginx.conf /etc/nginx/hub/nginx.conf
COPY --from=build /web/dist /usr/share/nginx/html
# Beveiligingsupdates van Alpine meenemen (standaard aan).
ARG APK_UPGRADE=true
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/ca_bundle PIP_CERT=/run/secrets/ca_bundle NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi; \
    if [ "$APK_UPGRADE" = "true" ]; then apk upgrade --no-cache; fi \
 && rm -f /docker-entrypoint.sh && rm -rf /docker-entrypoint.d \
 && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
 && rm -rf /sbin/apk /etc/apk /lib/apk /usr/share/apk /var/cache/apk \
 && rm -f /bin/busybox /bin/sh
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/usr/sbin/nginx"]
CMD ["-c", "/etc/nginx/hub/nginx.conf", "-e", "/dev/stderr", "-g", "daemon off;"]
