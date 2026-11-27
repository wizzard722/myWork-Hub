# Web-schil: bouwen op Chainguard node (dev), serveren op Chainguard nginx
# (geen shell, niet-root, uid 65532).
ARG NODE_BUILD_IMAGE=cgr.dev/chainguard/node:latest-dev
ARG NGINX_IMAGE=cgr.dev/chainguard/nginx:latest

FROM ${NODE_BUILD_IMAGE} AS build
USER root
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM ${NGINX_IMAGE}
COPY nginx.conf /etc/nginx/hub/nginx.conf
COPY --from=build /web/dist /usr/share/nginx/html
USER 65532
EXPOSE 8080
ENTRYPOINT ["/usr/sbin/nginx"]
CMD ["-c", "/etc/nginx/hub/nginx.conf", "-e", "/dev/stderr", "-g", "daemon off;"]
