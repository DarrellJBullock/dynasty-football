#!/usr/bin/env bash
# Sets up this Mac as the self-hosted GitHub Actions runner for the Unity workflow
# (.github/workflows/unity.yml; docs/unity.md). Run it yourself, once, on the Mac that has
# Unity installed and signed in:
#
#   scripts/setup-unity-runner.sh
#
# It downloads GitHub's official runner for Apple Silicon (checking its SHA-256 against
# the release's published value), registers it to this repository with the label `unity`
# (the registration token is fetched with your `gh` login and never printed), installs it
# as a login item that runs as you (so Unity's licensing works), and sets the repository
# variable UNITY_RUNNER=true so the Unity workflow starts using it.
#
# To remove it later:  cd ~/actions-runner-dynasty && ./svc.sh uninstall &&
#   ./config.sh remove --token "$(gh api -X POST repos/<repo>/actions/runners/remove-token --jq .token)"
#   and: gh variable delete UNITY_RUNNER -R <repo>
set -euo pipefail

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
DIR="${RUNNER_DIR:-$HOME/actions-runner-dynasty}"
[ "$(uname -s)-$(uname -m)" = "Darwin-arm64" ] || { echo "This script is for an Apple Silicon Mac."; exit 1; }
[ -f "$DIR/.runner" ] && { echo "A runner is already set up in $DIR."; exit 0; }

TAG=$(gh api repos/actions/runner/releases/latest --jq .tag_name)
VERSION=${TAG#v}
ARCHIVE="actions-runner-osx-arm64-$VERSION.tar.gz"
echo "Downloading GitHub's runner $VERSION into $DIR …"
mkdir -p "$DIR"
cd "$DIR"
curl -fsSL -o "$ARCHIVE" "https://github.com/actions/runner/releases/download/$TAG/$ARCHIVE"
EXPECTED=$(gh api "repos/actions/runner/releases/tags/$TAG" --jq .body \
  | sed -n 's/.*<!-- BEGIN SHA osx-arm64 -->\([0-9a-f]*\)<!-- END SHA osx-arm64 -->.*/\1/p')
[ -n "$EXPECTED" ] || { echo "Couldn't find the published checksum; stopping."; exit 1; }
echo "$EXPECTED  $ARCHIVE" | shasum -a 256 -c -
tar xzf "$ARCHIVE"
rm "$ARCHIVE"

echo "Registering it to $REPO …"
TOKEN=$(gh api -X POST "repos/$REPO/actions/runners/registration-token" --jq .token)
./config.sh --unattended --url "https://github.com/$REPO" --token "$TOKEN" \
  --name "$(scutil --get LocalHostName)-unity" --labels unity --work _work --replace
unset TOKEN

echo "Installing it as a login item (it runs as you, while you're logged in) …"
./svc.sh install
./svc.sh start

gh variable set UNITY_RUNNER --body true -R "$REPO"
echo "Done. The Unity workflow will now run on this Mac. Try it: Actions → Unity → Run workflow."
