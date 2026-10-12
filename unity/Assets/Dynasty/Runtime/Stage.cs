// The stadium (built like the browser's Stadium.tsx): the field painted by the page
// (fieldTexture.ts, sent as an image), goalposts, four banks of stands with a crowd half
// in the home colors, light towers, the lighting, the line of scrimmage and the line to
// gain, and the camera.
//
// Everything but the camera hangs from `Scene`, a root mirrored in z: under it, positions
// and rotations are the browser's three.js scene coordinates, number for number.

using System.Collections.Generic;
using UnityEngine;

namespace Dynasty.Playback
{
    public sealed class Stage
    {
        const float Border = 2; // the white border and team area outside the lines
        const float StandGap = 9;
        const int Rows = 14;
        const float RowDepth = 1.6f, RowRise = 1.1f, SeatSpacing = 1.1f;

        public readonly Camera Camera;
        public readonly Transform Scene;
        readonly Material surface;
        Transform lineOfScrimmage;
        Transform firstDown;
        Mesh crowd;

        public Stage(Transform parent)
        {
            Scene = new GameObject("Scene").transform;
            Scene.SetParent(parent, false);
            Scene.localScale = new Vector3(1, 1, -1);

            var cameraObject = new GameObject("Camera");
            cameraObject.transform.SetParent(parent, false);
            Camera = cameraObject.AddComponent<Camera>();
            Camera.clearFlags = CameraClearFlags.SolidColor;
            Camera.backgroundColor = new Color(0.04f, 0.06f, 0.1f);
            Camera.farClipPlane = 600;
            Camera.transform.SetPositionAndRotation(new Vector3(0, 34, -78), Quaternion.Euler(24, 0, 0));

            Lighting(parent);
            surface = Parts.Lit(Parts.Hex("#1d6b40"), 0.95f);
            Ground();
            GoalPost(0);
            GoalPost(Field.Length);
            Stands();
            LightTowers();
            lineOfScrimmage = Line("Line of scrimmage", Parts.Hex("#3b82f6"));
            firstDown = Line("Line to gain", Parts.Hex("#facc15"));
            Mark(null, null);
        }

        static void Lighting(Transform parent)
        {
            // The browser's hemisphere light (sky #cfe3ff, ground #14321f) and ambient, as
            // Unity's three-color ambient; then the key and fill lights. three.js divides its
            // light intensities by π (physically based units) and Unity doesn't, so these
            // are the browser's values over π, matched by eye.
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = Parts.Hex("#cfe3ff") * 0.42f;
            RenderSettings.ambientEquatorColor = Parts.Hex("#6f8a96") * 0.32f;
            RenderSettings.ambientGroundColor = Parts.Hex("#14321f") * 0.4f;
            void Sun(string name, Vector3 scenePosition, float intensity, LightShadows shadows)
            {
                var light = new GameObject(name).AddComponent<Light>();
                light.transform.SetParent(parent, false);
                light.type = LightType.Directional;
                light.intensity = intensity;
                light.shadows = shadows;
                light.shadowStrength = 0.6f;
                var from = Field.FromScene(scenePosition.x, scenePosition.y, scenePosition.z);
                light.transform.rotation = Quaternion.LookRotation(-from);
            }
            Sun("Key light", new Vector3(40, 80, 30), 0.62f, LightShadows.Soft);
            Sun("Fill light", new Vector3(-50, 60, -40), 0.22f, LightShadows.None);
        }

        void Ground()
        {
            Parts.Box(Scene, "Ground", new Vector3(0, -0.06f, 0), new Vector3(Field.Length + 60, 0.02f, Field.Width + 60),
                      Parts.Lit(Parts.Hex("#2a2f36"), 1));
            // The field surface: one quad, its texture mapped like the browser's canvas (the
            // canvas's top edge is the y = 0 sideline).
            float halfL = Field.Length / 2 + Border, halfW = Field.Width / 2 + Border;
            var mesh = new Mesh
            {
                vertices = new[]
                {
                    new Vector3(-halfL, 0, -halfW), new Vector3(halfL, 0, -halfW),
                    new Vector3(-halfL, 0, halfW), new Vector3(halfL, 0, halfW),
                },
                uv = new[] { new Vector2(0, 1), new Vector2(1, 1), new Vector2(0, 0), new Vector2(1, 0) },
                // Clockwise from above (Unity's front face; it handles the mirrored root itself).
                triangles = new[] { 0, 2, 1, 2, 3, 1 },
            };
            mesh.RecalculateNormals();
            var field = new GameObject("Field");
            field.transform.SetParent(Scene, false);
            field.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = field.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = surface;
            renderer.receiveShadows = true;
        }

        /// <summary>The field as the page painted it (a PNG).</summary>
        public void Paint(byte[] png)
        {
            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, true) { anisoLevel = 8 };
            if (!texture.LoadImage(png)) throw new System.FormatException("The field image didn't decode.");
            texture.wrapMode = TextureWrapMode.Clamp;
            surface.color = Color.white;
            var old = surface.mainTexture;
            surface.mainTexture = texture;
            if (old) Parts.Remove(old);
        }

        void GoalPost(float x)
        {
            var post = Parts.Lit(Parts.Hex("#facc15"), 0.4f, 0.3f);
            float crossbar = 10f / 3, width = 18.5f / 3, upright = 35f / 3;
            float sx = x - Field.Length / 2;
            float outward = x == 0 ? -1 : 1;
            var group = Parts.Group(Scene, "Goalpost", new Vector3(sx, 0, 0));
            Parts.Cylinder(group, "Base", new Vector3(outward * 1.6f, crossbar / 2, 0), 0.18f, 0.22f, crossbar, post);
            var arm = Parts.Cylinder(group, "Arm", new Vector3(outward * 0.8f, crossbar, 0), 0.13f, 0.13f, 1.6f, post);
            arm.localRotation = Quaternion.Euler(0, 0, 90);
            var bar = Parts.Cylinder(group, "Crossbar", new Vector3(0, crossbar, 0), 0.12f, 0.12f, width, post);
            bar.localRotation = Quaternion.Euler(90, 0, 0);
            foreach (float z in new[] { -width / 2, width / 2 })
                Parts.Cylinder(group, "Upright", new Vector3(0, crossbar + upright / 2, z), 0.09f, 0.09f, upright, post);
        }

        readonly struct Section
        {
            public readonly float Cx, Cz, Along, Facing;
            public readonly bool Rotated;

            public Section(float cx, float cz, float along, float facing, bool rotated)
            {
                Cx = cx;
                Cz = cz;
                Along = along;
                Facing = facing;
                Rotated = rotated;
            }
        }

        static Section[] Sections()
        {
            float halfL = Field.Length / 2 + Border + StandGap, halfW = Field.Width / 2 + Border + StandGap;
            return new[]
            {
                new Section(0, halfW, Field.Length + 10, 1, false), new Section(0, -halfW, Field.Length + 10, -1, false),
                new Section(halfL, 0, Field.Width + 10, 1, true), new Section(-halfL, 0, Field.Width + 10, -1, true),
            };
        }

        void Stands()
        {
            var concrete = new MeshBuilder();
            foreach (var s in Sections())
            {
                for (int row = 0; row < Rows; row++)
                {
                    float depth = row * RowDepth + RowDepth / 2, height = (row + 1) * RowRise;
                    var center = s.Rotated ? new Vector3(s.Cx + s.Facing * depth, height / 2, 0)
                                           : new Vector3(0, height / 2, s.Cz + s.Facing * depth);
                    var size = s.Rotated ? new Vector3(RowDepth, height, s.Along) : new Vector3(s.Along, height, RowDepth);
                    concrete.Box(center, size, Parts.Hex(row % 2 == 1 ? "#3a414b" : "#343a43"));
                }
            }
            Mesh("Stands", concrete.Build());
            crowd = new Mesh();
            Mesh("Crowd", crowd);
            Crowd(new[] { Parts.Hex("#6b7280"), Parts.Hex("#9ca3af") });
        }

        /// <summary>The fans, about half of them in the home team's colors (seeded, like the
        /// browser's, so the crowd is the same every time).</summary>
        public void Crowd(Color[] homeColors)
        {
            uint state = 7;
            double Random()
            {
                state = unchecked(state * 1664525 + 1013904223);
                return state / 4294967296.0;
            }
            var palette = new List<Color>(homeColors);
            palette.AddRange(new[] { Parts.Hex("#e5e7eb"), Parts.Hex("#4b5563"), Parts.Hex("#1f2937"), Parts.Hex("#9ca3af") });
            var fans = new MeshBuilder();
            foreach (var s in Sections())
            {
                int count = Mathf.FloorToInt(s.Along / SeatSpacing);
                for (int row = 0; row < Rows; row++)
                {
                    float depth = row * RowDepth + RowDepth / 2, height = row * RowRise + RowRise + 0.45f;
                    for (int i = 0; i < count; i++)
                    {
                        float along = -s.Along / 2 + (i + 0.5f) * SeatSpacing;
                        float y = height + (float)Random() * 0.15f;
                        var at = s.Rotated ? new Vector3(s.Cx + s.Facing * depth, y, along)
                                           : new Vector3(along, y, s.Cz + s.Facing * depth);
                        int pick = Random() < 0.5 ? (int)(Random() * homeColors.Length)
                                                  : homeColors.Length + (int)(Random() * 4);
                        fans.Box(at, new Vector3(0.7f, 0.9f, 0.5f), palette[pick]);
                    }
                }
            }
            fans.Into(crowd);
        }

        void Mesh(string name, Mesh mesh)
        {
            var go = new GameObject(name);
            go.transform.SetParent(Scene, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            go.AddComponent<MeshRenderer>().sharedMaterial = Resources.Load<Material>("Crowd");
        }

        void LightTowers()
        {
            float x = Field.Length / 2 + Border + StandGap + Rows * RowDepth * 0.8f;
            float z = Field.Width / 2 + Border + StandGap + Rows * RowDepth * 0.8f;
            var pole = Parts.Lit(Parts.Hex("#6b7280"), 0.5f, 0.4f);
            var lamps = new Material(Resources.Load<Material>("Lamps"));
            foreach (var (tx, tz) in new[] { (x, z), (-x, z), (x, -z), (-x, -z) })
            {
                var tower = Parts.Group(Scene, "Light tower", new Vector3(tx, 0, tz));
                Parts.Cylinder(tower, "Pole", new Vector3(0, 24, 0), 0.5f, 0.8f, 48, pole);
                var bank = Parts.Box(tower, "Lamps", new Vector3(0, 49, 0), new Vector3(9, 4, 0.8f), lamps);
                // (three.js applies its Euler angles X then Y: rotation-x −0.35 after rotation-y.)
                bank.localRotation = Quaternion.Euler(Parts.Deg(-0.35), 0, 0)
                                     * Quaternion.Euler(0, Parts.Deg(Mathf.Atan2(tx, tz)), 0);
            }
        }

        Transform Line(string name, Color color)
        {
            var line = Parts.Box(Scene, name, Vector3.zero, new Vector3(0.3f, 0.01f, Field.Width), Parts.Unlit(color));
            line.GetComponent<Renderer>().shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            return line;
        }

        /// <summary>The line of scrimmage and the line to gain (field x), or hidden.</summary>
        public void Mark(double? los, double? firstDownLine)
        {
            Place(lineOfScrimmage, los);
            Place(firstDown, firstDownLine);
        }

        static void Place(Transform marker, double? x)
        {
            marker.gameObject.SetActive(x.HasValue);
            if (x.HasValue) marker.localPosition = Field.ToScene(x.Value, Field.Width / 2, 0.02);
        }

        public void Aim(Frame frame)
        {
            Camera.transform.position = frame.Position;
            Camera.transform.LookAt(frame.Target);
            Camera.fieldOfView = frame.Fov;
        }
    }

    /// <summary>Many colored boxes as one mesh (the stands, the crowd).</summary>
    public sealed class MeshBuilder
    {
        readonly List<Vector3> vertices = new();
        readonly List<Vector3> normals = new();
        readonly List<Color> colors = new();
        readonly List<int> triangles = new();

        static readonly Vector3[] Faces = { Vector3.right, Vector3.left, Vector3.up, Vector3.down, Vector3.forward, Vector3.back };

        public void Box(Vector3 center, Vector3 size, Color color)
        {
            var half = size / 2;
            foreach (var n in Faces)
            {
                // Two axes across the face, so (u × v) points along n.
                var u = new Vector3(n.y, n.z, n.x);
                var v = Vector3.Cross(n, u);
                int start = vertices.Count;
                foreach (var (a, b) in new[] { (-1, -1), (1, -1), (1, 1), (-1, 1) })
                {
                    vertices.Add(center + Vector3.Scale(n + a * u + b * v, half));
                    normals.Add(n);
                    colors.Add(color);
                }
                // Clockwise seen from outside the face (Unity's front face).
                triangles.AddRange(new[] { start, start + 1, start + 2, start, start + 2, start + 3 });
            }
        }

        public Mesh Build()
        {
            var mesh = new Mesh();
            Into(mesh);
            return mesh;
        }

        public void Into(Mesh mesh)
        {
            mesh.Clear();
            mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetColors(colors);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
        }
    }
}
