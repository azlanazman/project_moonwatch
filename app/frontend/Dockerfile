# ---------------------------------------------------------------------------
# NGINX frontend image
#
# Uses the official nginx:stable-alpine base — small footprint (~25 MB).
# enterprise: alpine-based images are preferred in enterprise registries
# because they have a smaller CVE surface than debian/ubuntu variants.
# ---------------------------------------------------------------------------
FROM nginx:stable-alpine

# Replace the default NGINX config with our custom one
COPY nginx.conf /etc/nginx/nginx.conf

# Copy static HTML into the default web root
COPY index.html /usr/share/nginx/html/index.html

# NGINX listens on 80 inside the container;
# the host-facing port mapping is set in docker-compose.yml
EXPOSE 80

# nginx:stable-alpine already sets CMD ["nginx", "-g", "daemon off;"]
# so no CMD override needed here
