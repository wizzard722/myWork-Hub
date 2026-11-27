FROM nginxinc/nginx-unprivileged:1.27-alpine
# Alleen deze variabelen invullen; nginx-variabelen zoals $host blijven staan.
ENV NGINX_ENVSUBST_FILTER="^(NGINX_RESOLVER|HUB_SERVICE_SUFFIX)$" \
    NGINX_RESOLVER=127.0.0.11 \
    HUB_SERVICE_SUFFIX=""
COPY default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
