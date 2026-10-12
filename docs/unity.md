# The Unity viewer

A second 3D renderer for the Watch page, beside the classic React Three Fiber one
(design: [design/depth-and-unity.md](design/depth-and-unity.md) §4). The browser still
builds every play's timeline, runs the playhead, the broadcast director, the camera and
the overlay; Unity only draws, from the same timeline, with the camera the page sends it
each frame.

```
unity/                       the Unity project (Unity 6, the version in ProjectSettings/ProjectVersion.txt)
  Assets/Dynasty/Runtime/    Timeline.cs (the timeline), TimelineSampler.cs (timeline.ts ported),
                             Poses.cs (poses.ts ported), Field.cs (coordinates),
                             Stage.cs (the stadium, lighting, camera), Athlete.cs (a player),
                             PlayView.cs (the players, ball, flag), Parts.cs (shapes sized
                             like three.js's), Bridge.cs (the page's messages)
  Assets/Dynasty/Shaders/    VertexColorLit.shader (the stands and crowd)
  Assets/Dynasty/Plugins/WebGL/DynastyBridge.jslib   Unity → page events
  Assets/Dynasty/Editor/BuildScript.cs               Setup() and BuildWebGL()
  Assets/Dynasty/Tests/      edit-mode tests; Fixtures/timelines.json is written by the frontend
frontend/src/lib/unity.ts                            the page's side: find, start, message
frontend/src/components/field/unity/UnityPlayScene.tsx   the Unity scene (PlayScene's props)
frontend/public/unity/       the WebGL build (not committed)
```

## Working on it

Install Unity Hub and the editor version in `unity/ProjectSettings/ProjectVersion.txt`
with **WebGL Build Support**, and sign in (Unity Personal is fine).

```
make unity-test     # edit-mode tests (results in unity/Logs/test-results.xml)
make unity-build    # WebGL build into frontend/public/unity (about 1.5 minutes, ~8 MB)
```

With a build in `frontend/public/unity/`, the Watch page's **Renderer** switch offers
**Unity**; `e2e/unity.spec.ts` runs too (it skips without a build). The choice is kept in
the browser; if Unity can't start (no WebGL 2, a failed download), the page goes back to
Classic, says so, and remembers that.

**Coordinates:** everything but the camera hangs from `Stage.Scene`, mirrored in z, so
models are built in the browser's three.js scene coordinates with its numbers. Unity's
Euler angles match three.js's for one axis or for X with Z; where three.js combines X then
Y, multiply `Quaternion.Euler(x, 0, 0) * Quaternion.Euler(0, y, 0)`. Check orientation in
tests with `TransformVector` (it includes the mirroring scales), not `TransformDirection`.

**The two samplers must agree.** `TimelineSampler.cs` is a port of `timeline.ts`. When the
choreographer or the sampler changes, rewrite the shared fixtures and run both sides:

```
cd frontend && UPDATE_UNITY_FIXTURES=1 npx vitest run src/components/field/unity/fixtures.test.ts
make unity-test
```

## One Unity per page

Starting Unity takes seconds, and Coach Mode shows a new reel after every call, so the page
keeps one running: `leaseUnity` (lib/unity.ts) lends its canvas to whichever viewer is
shown and parks it, hidden and idle, between them. Components never call `startUnity`
themselves. The Renderer switch and its remembered choice are shared by the Watch page and
Coach Mode (`field/unity/renderer.tsx`).

## Messages

The page → Unity (`SendMessage("Bridge", …)`):

- `SetField` — `{"image": "<base64 PNG>", "crowd": ["#home", "#colors"]}`: the field as
  the page paints it (fieldTexture.ts), once per game, and the home fans' colors
- `LoadPlay` — `{"timeline": …, "kits": {"<team id>": {"jersey", "numbers", "pants",
  "helmet", "socks"}}}`
- `SetFrame` — `"t,px,py,pz,tx,ty,tz,fov"`: the playhead, and the camera's position and
  target in three.js scene coordinates (Unity flips Z) with its vertical field of view.
- `SetActive` — `"1"` while a viewer shows it, `"0"` when parked (camera off, 2 fps).

Unity → the page: a `dynasty-unity` event on `window` with `{type, detail}`: `ready`
(the stage is built), `loaded` (a play, with its figure count), `error` (a message).

## CI and deployment

**Why a self-hosted runner.** GameCI on GitHub's Linux machines was tried with a Unity
Personal license (2026-10-12) and rejected twice: the license file is bound to the Mac that
made it ("Machine bindings don't match"), and the account sign-in fallback was refused
("Invalid Credential", which is what two-factor authentication, a pending new-device check
or a sign-in without a password produce). So the Unity build runs on the Mac that already
has Unity installed and signed in, as a self-hosted GitHub Actions runner. No Unity
secrets are needed (delete `UNITY_LICENSE`, `UNITY_EMAIL` and `UNITY_PASSWORD` if they
exist).

**Set it up** (once, on that Mac, yourself):

```
scripts/setup-unity-runner.sh
```

It downloads GitHub's official runner (checking the published SHA-256), registers it to
this repository with the label `unity` (the token comes from your `gh` login and isn't
printed), installs it as a login item that runs as you (so Unity's licensing works), and
sets the repository variable `UNITY_RUNNER=true`. Then: Actions → Unity → Run workflow.

**The Unity workflow** (`.github/workflows/unity.yml`) runs `make unity-test` and
`make unity-build` and uploads the build as `unity-webgl`. It runs only for pushes to
`main`, pull requests from this repository's own branches and runs started by hand (never
for someone else's fork: the repository is public), and only while `UNITY_RUNNER` is
`true`. It's separate from CI, so a Mac that's off or asleep never holds CI up; its runs
just wait for the Mac. The deploy workflow ships the latest successful build from `main`
(or none, and the site runs without the Unity renderer).

**Safeguards for a public repository:** keep Settings → Actions → General → "Require
approval for all external contributors" on; the workflow's own condition also refuses
forks. The runner runs only this repository's Unity workflow (its label), as your user.

**Limitations:** the Mac must be on, awake and logged in for Unity runs; Unity's e2e specs
(`e2e/unity.spec.ts`) run locally with `make e2e` after `make unity-build`, not in CI.

**To remove it:** `cd ~/actions-runner-dynasty && ./svc.sh uninstall`, then
`./config.sh remove --token "$(gh api -X POST repos/DarrellJBullock/dynasty-football/actions/runners/remove-token --jq .token)"`
and `gh variable delete UNITY_RUNNER -R DarrellJBullock/dynasty-football`.

GameCI's Docker images are per editor version; if Unity Pro (a serial) or a dedicated CI
account ever makes GitHub-hosted builds possible, GameCI publishes
`unityci/editor:ubuntu-6000.6.5f1-webgl-3` for this version.
