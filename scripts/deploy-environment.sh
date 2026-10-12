#!/usr/bin/env bash
# Deploy this commit's images ($REGISTRY, $SHA) to one environment's Render services,
# then check the site is ready:
#   scripts/deploy-environment.sh API_SERVICE_ID WORKER_SERVICE_ID WEB_SERVICE_ID SITE_URL
# The API goes first (its pre-deploy step migrates the database), then the worker, then
# the web app. Without RENDER_API_KEY (not set up yet) it says so and stops.
set -euo pipefail
api_service=$1 worker_service=$2 web_service=$3 site=$4
if [ -z "${RENDER_API_KEY:-}" ] || [ -z "$api_service" ]; then
  echo "::notice::Render isn't set up for this environment yet (docs/deploy.md); skipping the deploy."
  exit 0
fi
here=$(dirname "$0")
"$here/render-deploy.sh" "$api_service" "$REGISTRY/dynasty-football-api:$SHA"
"$here/render-deploy.sh" "$worker_service" "$REGISTRY/dynasty-football-api:$SHA"
"$here/render-deploy.sh" "$web_service" "$REGISTRY/dynasty-football-web:$SHA"
if [ -n "$site" ]; then
  curl -fsS --retry 10 --retry-delay 6 --retry-all-errors "$site/api/ready"
  echo
fi
