#!/usr/bin/env bash
# Deploy an image to a Render service and wait until it's live (or fails):
#   scripts/render-deploy.sh SERVICE_ID IMAGE_URL     (with RENDER_API_KEY set)
# For the API, Render runs its pre-deploy step (migrations) before switching over.
set -euo pipefail
service=$1 image=$2
: "${RENDER_API_KEY:?set RENDER_API_KEY}"
api=https://api.render.com/v1
auth=(-H "Authorization: Bearer $RENDER_API_KEY" -H "Accept: application/json")

deploy=$(curl -fsS "${auth[@]}" -H "Content-Type: application/json" \
  -d "{\"imageUrl\": \"$image\"}" "$api/services/$service/deploys")
id=$(echo "$deploy" | jq -r .id)
echo "deploy $id of $image to $service"

for _ in $(seq 120); do  # up to 20 minutes
  status=$(curl -fsS "${auth[@]}" "$api/services/$service/deploys/$id" | jq -r .status)
  case $status in
    live) echo "live"; exit 0 ;;
    build_failed|update_failed|pre_deploy_failed|canceled|deactivated)
      echo "deploy $id: $status"; exit 1 ;;
  esac
  sleep 10
done
echo "deploy $id still $status after 20 minutes"; exit 1
