# Publieke reverse proxy: Caddy (Alpine), gehardend: geen shell, geen apk, niet-root.
# Poorten 80/443 als niet-root: in Compose via sysctl net.ipv4.ip_unprivileged_port_start=0;
# daarom zonder file-capability (die botst met cap_drop: ALL).
ARG CADDY_IMAGE=caddy:2.10-alpine
FROM ${CADDY_IMAGE}
COPY Caddyfile /etc/caddy/Caddyfile
# Beveiligingsupdates van Alpine meenemen (standaard aan).
ARG APK_UPGRADE=true
RUN if [ "$APK_UPGRADE" = "true" ]; then apk upgrade --no-cache; fi \
 && setcap -r /usr/bin/caddy \
 && mkdir -p /data /config && chown -R 65532:65532 /data /config \
 && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
 && rm -rf /sbin/apk /etc/apk /lib/apk /usr/share/apk /var/cache/apk \
 && rm -f /bin/busybox /bin/sh
ENV XDG_DATA_HOME=/data XDG_CONFIG_HOME=/config
USER 65532:65532
EXPOSE 80 443 443/udp
ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
