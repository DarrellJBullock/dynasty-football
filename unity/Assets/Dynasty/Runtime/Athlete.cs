// A player: helmet and facemask, pads, jersey with numbers, pants, socks and shoes, on a
// jointed skeleton posed every frame. Built like the browser's PlayerFigure.tsx, part for
// part, in the browser's scene coordinates (the figure faces +x, its right side is +z).

using UnityEngine;

namespace Dynasty.Playback
{
    /// <summary>A team's uniform (players/kit.ts) and a player's skin.</summary>
    public readonly struct Kit
    {
        public readonly Color Jersey, Numbers, Pants, Helmet, Socks;

        public Kit(Color jersey, Color numbers, Color pants, Color helmet, Color socks)
        {
            Jersey = jersey;
            Numbers = numbers;
            Pants = pants;
            Helmet = helmet;
            Socks = socks;
        }

        public static readonly Kit Plain = new(Color.gray, Color.white, Color.gray, Color.gray, Color.gray);

        static readonly string[] Skins = { "#f1c9a5", "#e0ac83", "#c68b59", "#a8693f", "#8d5524", "#6b3e1f", "#4a2a17" };

        /// <summary>A stable skin tone per player (kit.ts skinTone).</summary>
        public static string SkinTone(int playerId)
        {
            int mixed = unchecked((int)((uint)playerId * 2654435761u)); // Math.imul
            return Skins[System.Math.Abs((long)mixed) % Skins.Length];
        }
    }

    public sealed class Athlete
    {
        readonly Build build;
        readonly Transform root, body, torso, hipL, hipR, kneeL, kneeR, shoulderL, shoulderR, elbowL, elbowR;

        public Transform Root => root;

        public Athlete(Transform parent, TimelinePlayer player, Kit kit, Font font)
        {
            build = new Build(player.HeightIn, player.WeightLb);
            var b = build;
            float w = (float)b.Bulk;
            float thigh = (float)b.Thigh, shin = (float)b.Shin, torsoLength = (float)b.Torso, head = (float)b.Head;
            float upperArm = (float)b.UpperArm, forearm = (float)b.Forearm;

            var jersey = Parts.Lit(kit.Jersey, 0.7f);
            var pants = Parts.Lit(kit.Pants, 0.7f);
            var helmet = Parts.Lit(kit.Helmet, 0.25f, 0.35f);
            var socks = Parts.Lit(kit.Socks, 0.8f);
            var skin = Parts.Lit(Parts.Hex(Kit.SkinTone(player.Id)), 0.8f);
            var dark = Parts.Lit(Parts.Hex("#111827"), 0.6f);
            var mask = Parts.Lit(Parts.Hex("#d1d5db"), 0.4f, 0.5f);

            root = Parts.Group(parent, $"{player.Side} {player.Role} #{player.Number}");
            body = Parts.Group(root, "Body");
            Parts.Box(body, "Pelvis", new Vector3(0, 0.02f, 0), new Vector3(0.22f * w, 0.2f, 0.36f * w), pants);

            Transform Leg(string side, float z, out Transform knee)
            {
                var hip = Parts.Group(body, $"Hip {side}", new Vector3(0, 0, z));
                Parts.Capsule(hip, "Thigh", new Vector3(0, -thigh / 2, 0), 0.075f * w, thigh - 0.1f, pants);
                knee = Parts.Group(hip, $"Knee {side}", new Vector3(0, -thigh, 0));
                Parts.Capsule(knee, "Shin", new Vector3(0, -shin / 2, 0), 0.058f * w, shin - 0.08f, socks);
                Parts.Box(knee, "Shoe", new Vector3(0.05f, -shin + 0.02f, 0), new Vector3(0.2f, 0.07f, 0.1f), dark);
                return hip;
            }
            hipL = Leg("L", -0.11f * w, out kneeL);
            hipR = Leg("R", 0.11f * w, out kneeR);

            torso = Parts.Group(body, "Torso", new Vector3(0, 0.08f, 0));
            Parts.Cylinder(torso, "Jersey", new Vector3(0, torsoLength / 2, 0), 0.2f * w, 0.15f * w, torsoLength, jersey);
            Parts.Box(torso, "Pads", new Vector3(0, torsoLength * 0.92f, 0), new Vector3(0.32f * w, 0.14f, 0.62f * w), jersey);
            foreach (int side in new[] { 1, -1 })
                Number(torso, player.Number, kit.Numbers, font, new Vector3(side * 0.21f * w, torsoLength * 0.6f, 0), side);
            var helmetGroup = Parts.Group(torso, "Head", new Vector3(0, torsoLength + head * 0.55f, 0));
            Parts.Sphere(helmetGroup, "Helmet", Vector3.zero, head * 0.55f, helmet);
            Parts.Box(helmetGroup, "Facemask", new Vector3(head * 0.45f, -head * 0.12f, 0),
                      new Vector3(0.04f, head * 0.45f, head * 0.7f), mask);

            Transform Arm(string side, float z, out Transform elbow)
            {
                var shoulder = Parts.Group(torso, $"Shoulder {side}", new Vector3(0, torsoLength * 0.9f, z));
                Parts.Capsule(shoulder, "Upper arm", new Vector3(0, -upperArm / 2, 0), 0.055f * w, upperArm - 0.08f, jersey);
                elbow = Parts.Group(shoulder, $"Elbow {side}", new Vector3(0, -upperArm, 0));
                Parts.Capsule(elbow, "Forearm", new Vector3(0, -forearm / 2, 0), 0.045f * w, forearm - 0.08f, skin);
                Parts.Sphere(elbow, "Glove", new Vector3(0, -forearm, 0), 0.05f, dark);
                return shoulder;
            }
            shoulderL = Arm("L", -0.27f * w, out elbowL);
            shoulderR = Arm("R", 0.27f * w, out elbowR);
        }

        /// <summary>The number on the chest (side 1, facing +x) or the back (−1).</summary>
        static void Number(Transform torso, int number, Color color, Font font, Vector3 position, int side)
        {
            var text = new GameObject(side > 0 ? "Number (chest)" : "Number (back)");
            var t = text.transform;
            t.SetParent(torso, false);
            t.localPosition = position;
            // A TextMesh reads from −z; turn it to face outward, and flip x back under the
            // mirrored root so the digits aren't reversed.
            t.localRotation = Quaternion.Euler(0, side > 0 ? -90 : 90, 0);
            t.localScale = new Vector3(-0.026f, 0.026f, 0.026f);
            var mesh = text.AddComponent<TextMesh>();
            mesh.text = number.ToString();
            mesh.font = font;
            mesh.fontSize = 64;
            mesh.characterSize = 0.1f;
            mesh.fontStyle = FontStyle.Bold;
            mesh.anchor = TextAnchor.MiddleCenter;
            mesh.alignment = TextAlignment.Center;
            mesh.color = color;
            text.GetComponent<MeshRenderer>().sharedMaterial = font.material;
        }

        /// <summary>Stand him at (x, y) on the field, facing <paramref name="facing"/>, in a pose.</summary>
        public void Pose(double x, double y, double facing, JointAngles a)
        {
            root.localPosition = Field.ToScene(x, y);
            root.localRotation = Quaternion.Euler(0, Parts.Deg(-facing), 0);
            body.localPosition = new Vector3(0, (float)build.HipHeight(a), 0);
            body.localRotation = Quaternion.Euler(0, 0, Parts.Deg(-a.Lie * (Mathf.PI / 2) * 0.95));
            torso.localRotation = Quaternion.Euler(0, 0, Parts.Deg(-a.Torso));
            hipL.localRotation = Quaternion.Euler(0, 0, Parts.Deg(a.HipL));
            hipR.localRotation = Quaternion.Euler(0, 0, Parts.Deg(a.HipR));
            kneeL.localRotation = Quaternion.Euler(0, 0, Parts.Deg(-a.KneeL));
            kneeR.localRotation = Quaternion.Euler(0, 0, Parts.Deg(-a.KneeR));
            shoulderL.localRotation = Quaternion.Euler(Parts.Deg(a.SpreadL), 0, Parts.Deg(a.ShoulderL));
            shoulderR.localRotation = Quaternion.Euler(Parts.Deg(-a.SpreadR), 0, Parts.Deg(a.ShoulderR));
            elbowL.localRotation = Quaternion.Euler(0, 0, Parts.Deg(a.ElbowL));
            elbowR.localRotation = Quaternion.Euler(0, 0, Parts.Deg(a.ElbowR));
        }
    }
}
