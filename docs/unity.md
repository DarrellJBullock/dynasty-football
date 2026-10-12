# The Unity viewer

A second 3D renderer for the Watch page, beside the classic React Three Fiber one
(design: [design/depth-and-unity.md](design/depth-and-unity.md) §4). The browser still
builds every play's timeline, runs the playhead, the broadcast director, the camera and
the overlay; Unity only draws, from the same timeline, with the camera the page sends it
each frame.

```
unity/                       the Unity project (Unity 6, the version in ProjectSettings/ProjectVersion.txt)
  Assets/Dynasty/Runtime/    Timeline.cs (the timeline), TimelineSampler.cs (timeline.ts ported),
                             Field.cs (coordinates), Stage.cs (field, light, camera),
                             PlayView.cs (the players, ball, flag), Bridge.cs (the page's messages)
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

**The two samplers must agree.** `TimelineSampler.cs` is a port of `timeline.ts`. When the
choreographer or the sampler changes, rewrite the shared fixtures and run both sides:

```
cd frontend && UPDATE_UNITY_FIXTURES=1 npx vitest run src/components/field/unity/fixtures.test.ts
make unity-test
```

## Messages

The page → Unity (`SendMessage("Bridge", …)`):

- `LoadPlay` — `{"timeline": …, "teams": {"<team id>": "#jersey"}, "endZone": "#color"}`
- `SetFrame` — `"t,px,py,pz,tx,ty,tz,fov"`: the playhead, and the camera's position and
  target in three.js scene coordinates (Unity flips Z) with its vertical field of view.

Unity → the page: a `dynasty-unity` event on `window` with `{type, detail}`: `ready`
(the stage is built), `loaded` (a play, with its figure count), `error` (a message).

## CI and deployment

CI's **Unity** job runs the edit-mode tests and the WebGL build with
[GameCI](https://game.ci), uploads the build as the `unity-webgl` artifact, and the e2e
and container-image jobs (and the deploy workflow) put it in `frontend/public/unity/`.
It needs a Unity license in the repository's secrets; without one the job skips with a
notice and the site runs without the Unity renderer.

To turn it on, follow GameCI's activation guide for a Personal license
(<https://game.ci/docs/github/activation>) and add these repository secrets
(Settings → Secrets and variables → Actions):

- `UNITY_LICENSE`: the contents of the `.ulf` license file GameCI's guide produces
- `UNITY_EMAIL` and `UNITY_PASSWORD`: the Unity ID that license belongs to

GameCI's Docker images are per editor version; when the project moves to a new Unity
version, check that GameCI publishes an image for it.
