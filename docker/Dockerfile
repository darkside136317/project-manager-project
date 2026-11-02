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
