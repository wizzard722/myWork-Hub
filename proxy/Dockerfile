# Publieke reverse proxy: Caddy, zelf gebouwd met de actuele Go-versie en bijgewerkte
# Go-bibliotheken (de officiële image liep achter met beveiligingsfixes), op Alpine.
# Gehardend: geen shell, geen apk, niet-root (uid 65532).
# Poorten 80/443 als niet-root: in Compose via sysctl net.ipv4.ip_unprivileged_port_start=0.
ARG GO_IMAGE=golang:1.27-alpine
ARG ALPINE_IMAGE=alpine:3.22

FROM ${GO_IMAGE} AS build
ARG CADDY_VERSION=v2.11.9
ENV CGO_ENABLED=0 GOFLAGS=-trimpath
WORKDIR /src
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -s /run/secrets/ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/ca_bundle; fi; \
    go mod init mywork-hub/caddy \
 && printf '%s\n' 'package main' \
      'import (' \
      '	caddycmd "github.com/caddyserver/caddy/v2/cmd"' \
      '	_ "github.com/caddyserver/caddy/v2/modules/standard"' \
      ')' \
      'func main() { caddycmd.Main() }' > main.go \
 && go get "github.com/caddyserver/caddy/v2@${CADDY_VERSION}" \
 && go get -u golang.org/x/net golang.org/x/crypto golang.org/x/text \
 && go mod tidy \
 && go build -ldflags="-s -w" -o /out/caddy . \
 && /out/caddy version

FROM ${ALPINE_IMAGE}
COPY --from=build /out/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
# Beveiligingsupdates van Alpine meenemen (standaard aan).
ARG APK_UPGRADE=true
RUN if [ "$APK_UPGRADE" = "true" ]; then apk upgrade --no-cache; fi \
 && mkdir -p /data /config && chown -R 65532:65532 /data /config \
 && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
 && rm -rf /sbin/apk /etc/apk /lib/apk /usr/share/apk /var/cache/apk \
 && rm -f /bin/busybox /bin/sh
ENV XDG_DATA_HOME=/data XDG_CONFIG_HOME=/config
USER 65532:65532
EXPOSE 80 443 443/udp
ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
