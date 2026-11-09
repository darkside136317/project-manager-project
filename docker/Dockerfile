# =============================================================================
# Frappe/ERPNext image with the project_manager and pm_construction apps
# =============================================================================
# Build context: repository root. scripts/bootstrap.* builds it through Compose;
# by hand (from the repository root):
#   docker build -t pm-custom:v16.26.2 --build-arg ERPNEXT_VERSION=v16.26.2 -f docker/Dockerfile .
# =============================================================================

ARG ERPNEXT_VERSION=v16.26.2

# -----------------------------------------------------------------------------
# Stage 1 - the single-page application (Vue 3 + Vite).
# vite.config.js writes the bundle to ../project_manager/public/spa.
# -----------------------------------------------------------------------------
FROM node:24.22.2-slim AS spa
WORKDIR /src/apps/project_manager/frontend
COPY apps/project_manager/frontend/package.json apps/project_manager/frontend/package-lock.json ./
RUN npm ci
COPY apps/project_manager/frontend/ ./
RUN npm test && npm run build

# -----------------------------------------------------------------------------
# Stage 2 - Frappe / ERPNext with the apps
# -----------------------------------------------------------------------------
FROM frappe/erpnext:${ERPNEXT_VERSION}

# Realtime (Socket.IO, the `websocket` service). Frappe's server accepts a connection only when the Origin and Host
# headers name the same host, then checks the user by calling the backend at that Origin, and the backend picks the
# site from the host name. The image's nginx sends Origin = the site name and Host = the browser's host: refused when
# the app is opened under another name (http://localhost:8890), and the site name does not resolve inside the
# containers. On /socket.io only, send http://<site>:8000 as both; compose gives the backend that name on the network.
USER root
RUN sed -i -e '/location \/socket.io/,/proxy_pass/ s|proxy_set_header Origin .*;|proxy_set_header Origin http://${FRAPPE_SITE_NAME_HEADER}:8000;|' \
           -e '/location \/socket.io/,/proxy_pass/ s|proxy_set_header Host \$host;|proxy_set_header Host ${FRAPPE_SITE_NAME_HEADER}:8000;|' \
        /templates/nginx/frappe.conf.template \
    && grep -q 'proxy_set_header Origin http://${FRAPPE_SITE_NAME_HEADER}:8000;' /templates/nginx/frappe.conf.template \
    && grep -q 'proxy_set_header Host ${FRAPPE_SITE_NAME_HEADER}:8000;' /templates/nginx/frappe.conf.template

USER frappe
WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:frappe apps/project_manager apps/project_manager
COPY --chown=frappe:frappe apps/pm_construction apps/pm_construction

# The SPA bundle (the host's public/spa is excluded by .dockerignore: always built here)
COPY --from=spa --chown=frappe:frappe /src/apps/project_manager/project_manager/public/spa apps/project_manager/project_manager/public/spa

# Install both apps into Frappe's virtualenv (not the system pip)
RUN env/bin/pip install --no-cache-dir -e apps/project_manager -e apps/pm_construction

# Expose the apps' public folders to nginx (bench build is not run in this image)
RUN ln -sfn /home/frappe/frappe-bench/apps/project_manager/project_manager/public assets/project_manager \
    && ln -sfn /home/frappe/frappe-bench/apps/pm_construction/pm_construction/public assets/pm_construction
