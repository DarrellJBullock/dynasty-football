#!/usr/bin/env bash
# Run the built images the way the host does, and check they work together:
#   scripts/smoke-test-images.sh API_IMAGE WEB_IMAGE   (with DATABASE_URL set)
# Migrates (the pre-deploy step), starts the API, the worker and the web app on the
# host network, then signs up through the web app and loads a page.
set -euo pipefail
api_image=$1 web_image=$2
: "${DATABASE_URL:?set DATABASE_URL}"

cleanup() {
  status=$?
  if [ $status -ne 0 ]; then
    for name in smoke-api smoke-worker smoke-web; do
      echo "--- $name logs"; docker logs $name 2>&1 | tail -40 || true
    done
  fi
  docker rm -f smoke-api smoke-worker smoke-web >/dev/null 2>&1 || true
  exit $status
}
trap cleanup EXIT

wait_for() {  # url expected-status
  for _ in $(seq 60); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "$1")" = "$2" ] && return 0
    sleep 1
  done
  echo "timed out waiting for $1 to answer $2"; return 1
}

docker run --rm --network host -e DATABASE_URL="$DATABASE_URL" "$api_image" alembic upgrade head
docker run -d --name smoke-api --network host -e DATABASE_URL="$DATABASE_URL" -e PORT=8000 \
  -e ALLOWED_ORIGINS='["http://localhost:3000"]' "$api_image"
docker run -d --name smoke-worker --network host -e DATABASE_URL="$DATABASE_URL" \
  "$api_image" python -m app.worker
docker run -d --name smoke-web --network host -e API_HOSTPORT=localhost:8000 -e PORT=3000 \
  "$web_image"

wait_for http://localhost:8000/api/ready 200
wait_for http://localhost:3000/signin 200
echo "API ready; web app up"

# Signed out, pages lead to sign in.
[ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/)" = 307 ]
# Through the web app's /api: readiness, then an account and its first (empty) state.
curl -fsS http://localhost:3000/api/ready | grep -q '"ready"'
jar=$(mktemp)
curl -fsS -c "$jar" -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.test","password":"smoke-test-password"}' \
  http://localhost:3000/api/auth/signup | grep -q '"has_league":false'
curl -fsS -b "$jar" http://localhost:3000/account | grep -q 'smoke@example.test\|Your account'
docker inspect -f '{{.State.Running}}' smoke-worker | grep -q true
echo "smoke test passed"
