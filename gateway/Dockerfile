# Gateway op het gehardende Chainguard nginx-image: geen shell, niet-root (uid 65532).
ARG NGINX_IMAGE=cgr.dev/chainguard/nginx:latest
FROM ${NGINX_IMAGE}
COPY nginx.conf env.conf /etc/nginx/hub/
USER 65532
EXPOSE 8080
ENTRYPOINT ["/usr/sbin/nginx"]
CMD ["-c", "/etc/nginx/hub/nginx.conf", "-e", "/dev/stderr", "-g", "daemon off;"]
