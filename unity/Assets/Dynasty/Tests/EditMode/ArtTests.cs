// The athletes and the stadium: built from the browser's numbers, posed as the timeline
// says, and drawn the right way round.

using System.Linq;
using Dynasty.Playback;
using NUnit.Framework;
using UnityEngine;

namespace Dynasty.Tests
{
    public class ArtTests
    {
        GameObject holder;

        [SetUp]
        public void MakeHolder() => holder = new GameObject("Test");

        [TearDown]
        public void RemoveHolder() => Object.DestroyImmediate(holder);

        static TimelinePlayer Player(int id = 12, int number = 88) => new()
        {
            Id = id, Side = "offense", TeamId = 1, Role = "WR1", Name = "G. Draper", Number = number,
            Position = "WR", HeightIn = 74, WeightLb = 200, Facing = 0,
            Path = new[] { new PathKey { T = 0, X = 60, Y = 20 } },
            Poses = new[] { new PoseKey { T = 0, Pose = "stand" } },
        };

        static Kit Uniform => new(Color.red, Color.white, Color.blue, Color.red, Color.red);

        [Test]
        public void AnAthleteStandsWhereTheTimelineSaysInHisPose()
        {
            var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var athlete = new Athlete(holder.transform, Player(), Uniform, font);
            var angles = Poses.Pose("stance3");
            athlete.Pose(70, 30, Mathf.PI / 2, angles);
            Assert.That(athlete.Root.localPosition, Is.EqualTo(Field.ToScene(70, 30)));
            var body = athlete.Root.Find("Body");
            Assert.That(body.localPosition.y, Is.EqualTo((float)new Build(74, 200).HipHeight(angles)).Within(1e-5f));
            var hip = body.Find("Hip L");
            Assert.That(hip.localEulerAngles.z, Is.EqualTo(Parts.Deg(angles.HipL)).Within(1e-3f));
            // Both numbers show his number, in the kit's color.
            var numbers = athlete.Root.GetComponentsInChildren<TextMesh>();
            Assert.That(numbers.Select(n => n.text), Is.EqualTo(new[] { "88", "88" }));
            Assert.That(numbers.All(n => n.color == Color.white));
        }

        [Test]
        public void TheChestNumberReadsLeftToRightFromTheFront()
        {
            // Under the mirrored root, as in the stage: the figure faces +x on the field.
            var scene = new GameObject("Scene").transform;
            scene.SetParent(holder.transform, false);
            scene.localScale = new Vector3(1, 1, -1);
            var athlete = new Athlete(scene, Player(), Uniform, Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf"));
            athlete.Pose(60, 26, 0, JointAngles.Zero);
            var chest = athlete.Root.GetComponentsInChildren<TextMesh>().First(n => n.name.Contains("chest")).transform;
            // A viewer in front (world +x) looking back at him: his right is world +z.
            var viewerRight = Vector3.Cross(Vector3.up, Vector3.left);
            // (TransformVector, not TransformDirection: the mirroring is in the scales.)
            Vector3 World(Vector3 local) => chest.TransformVector(local).normalized;
            Assert.That(Vector3.Dot(World(Vector3.right), viewerRight), Is.GreaterThan(0.9f), "reads left to right");
            // The text faces the viewer: a TextMesh shows its face on its −z side, and with
            // one mirror (x) in its own scale and one (z) in the root's, that's where it points.
            Assert.That(Vector3.Dot(World(Vector3.back), Vector3.right), Is.GreaterThan(0.9f), "faces him");
        }

        [Test]
        public void BoxesFaceOutward()
        {
            var builder = new MeshBuilder();
            builder.Box(Vector3.zero, new Vector3(2, 4, 6), Color.green);
            var mesh = builder.Build();
            var v = mesh.vertices;
            var t = mesh.triangles;
            Assert.That(t.Length, Is.EqualTo(36));
            for (int i = 0; i < t.Length; i += 3)
            {
                // Unity's front face winds clockwise: (b − a) × (c − a) points out of the box.
                var normal = Vector3.Cross(v[t[i + 1]] - v[t[i]], v[t[i + 2]] - v[t[i]]);
                var center = (v[t[i]] + v[t[i + 1]] + v[t[i + 2]]) / 3;
                Assert.That(Vector3.Dot(normal, center), Is.GreaterThan(0), $"triangle {i / 3}");
                Assert.That(Vector3.Dot(normal.normalized, mesh.normals[t[i]]), Is.GreaterThan(0.99f));
            }
        }

        [Test]
        public void TheStadiumIsBuiltOnceAndTheCrowdTakesTheHomeColors()
        {
            var stage = new Stage(holder.transform);
            var crowd = stage.Scene.Find("Crowd").GetComponent<MeshFilter>().sharedMesh;
            int fans = crowd.vertexCount / 24;
            Assert.That(fans, Is.GreaterThan(4000));
            stage.Crowd(new[] { Color.red, Color.blue });
            var colors = stage.Scene.Find("Crowd").GetComponent<MeshFilter>().sharedMesh.colors;
            Assert.That(colors.Length / 24, Is.EqualTo(fans)); // the same seats, recolored
            float home = colors.Where((_, i) => i % 24 == 0).Count(c => c == Color.red || c == Color.blue) / (float)fans;
            Assert.That(home, Is.InRange(0.4f, 0.6f)); // about half wear the home colors
            Assert.That(stage.Scene.GetComponentsInChildren<Transform>().Count(t => t.name == "Goalpost"), Is.EqualTo(2));
            Assert.That(stage.Scene.GetComponentsInChildren<Transform>().Count(t => t.name == "Light tower"), Is.EqualTo(4));
        }
    }
}
