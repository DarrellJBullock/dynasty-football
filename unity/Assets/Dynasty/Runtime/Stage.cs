// The stadium for the foundation: the field with its end zones and yard lines, the light,
// and the camera. Built in code (no scene authoring) from the materials in Resources/.

using UnityEngine;

namespace Dynasty.Playback
{
    public sealed class Stage
    {
        public readonly Camera Camera;
        readonly Material lit;
        readonly Material line;
        readonly Transform root;
        Transform lineOfScrimmage;
        Transform firstDown;
        Renderer[] endZones;

        public Stage(Transform parent)
        {
            lit = new Material(Resources.Load<Material>("Lit"));
            line = new Material(Resources.Load<Material>("Line"));
            root = new GameObject("Stage").transform;
            root.SetParent(parent, false);

            var cameraObject = new GameObject("Camera");
            cameraObject.transform.SetParent(root, false);
            Camera = cameraObject.AddComponent<Camera>();
            Camera.clearFlags = CameraClearFlags.SolidColor;
            Camera.backgroundColor = new Color(0.04f, 0.06f, 0.1f);
            Camera.farClipPlane = 600;
            Camera.transform.SetPositionAndRotation(new Vector3(0, 34, -78), Quaternion.Euler(24, 0, 0));

            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.transform.SetParent(root, false);
            sun.type = LightType.Directional;
            sun.intensity = 1.1f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(52, -30, 0);
            RenderSettings.ambientLight = new Color(0.45f, 0.48f, 0.55f);

            BuildField();
        }

        Transform Box(string name, Vector3 center, Vector3 size, Material material, Color color)
        {
            var box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            Object.Destroy(box.GetComponent<Collider>());
            box.name = name;
            box.transform.SetParent(root, false);
            box.transform.localPosition = center;
            box.transform.localScale = size;
            var renderer = box.GetComponent<Renderer>();
            renderer.sharedMaterial = material;
            renderer.material.color = color;
            return box.transform;
        }

        void BuildField()
        {
            var turf = new Color(0.16f, 0.42f, 0.2f);
            Box("Surround", new Vector3(0, -0.06f, 0), new Vector3(Field.Length + 16, 0.1f, Field.Width + 16),
                lit, new Color(0.12f, 0.3f, 0.15f));
            Box("Turf", new Vector3(0, -0.02f, 0), new Vector3(Field.Length, 0.04f, Field.Width), lit, turf);
            endZones = new[]
            {
                Box("End zone (left)", Field.ToWorld(Field.EndZone / 2, Field.Width / 2, -0.01),
                    new Vector3(Field.EndZone, 0.04f, Field.Width), lit, turf).GetComponent<Renderer>(),
                Box("End zone (right)", Field.ToWorld(Field.Length - Field.EndZone / 2, Field.Width / 2, -0.01),
                    new Vector3(Field.EndZone, 0.04f, Field.Width), lit, turf).GetComponent<Renderer>(),
            };
            for (int i = 0; i <= 20; i++)
            {
                float x = Field.EndZone + i * 5;
                Box($"Yard line {x}", Field.ToWorld(x, Field.Width / 2, 0.005),
                    new Vector3(i % 20 == 0 ? 0.35f : 0.15f, 0.01f, Field.Width), line, Color.white);
            }
            foreach (float y in new[] { 0f, Field.Width })
            {
                Box("Sideline", Field.ToWorld(Field.Length / 2, y, 0.005), new Vector3(Field.Length, 0.01f, 0.3f),
                    line, Color.white);
            }
            lineOfScrimmage = Box("Line of scrimmage", Vector3.zero, new Vector3(0.25f, 0.012f, Field.Width), line,
                                  new Color(0.3f, 0.55f, 1f));
            firstDown = Box("First down", Vector3.zero, new Vector3(0.25f, 0.012f, Field.Width), line,
                            new Color(1f, 0.85f, 0.2f));
            Mark(null, null);
        }

        /// <summary>The home team's colors in the end zones.</summary>
        public void Paint(Color endZone)
        {
            foreach (var r in endZones) r.material.color = endZone;
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
            if (x.HasValue) marker.localPosition = Field.ToWorld(x.Value, Field.Width / 2, 0.01);
        }

        public void Aim(Frame frame)
        {
            Camera.transform.position = frame.Position;
            Camera.transform.LookAt(frame.Target);
            Camera.fieldOfView = frame.Fov;
        }
    }
}
