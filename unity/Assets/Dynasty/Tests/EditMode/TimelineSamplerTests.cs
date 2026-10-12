// The sampler against the browser's own numbers: Fixtures/timelines.json holds timelines
// the choreographer built and timeline.ts's samples of them (written by the frontend test
// src/components/field/unity/fixtures.test.ts). The two viewers must agree.

using System.IO;
using System.Linq;
using Dynasty.Playback;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Dynasty.Tests
{
    public class TimelineSamplerTests
    {
        const double Tolerance = 1e-4;

        static JObject Fixtures() => JObject.Parse(File.ReadAllText(
            Path.Combine(Application.dataPath, "Dynasty/Tests/Fixtures/timelines.json")));

        static string[] Cases() => Fixtures()["cases"].Select(c => (string)c["name"]).ToArray();

        [TestCaseSource(nameof(Cases))]
        public void SamplesMatchTheBrowser(string name)
        {
            var fixture = Fixtures()["cases"].First(c => (string)c["name"] == name);
            var timeline = PlayTimeline.FromJson((JObject)fixture["timeline"]);
            var byId = timeline.Players.ToDictionary(p => p.Id);
            var samples = (JArray)fixture["samples"];
            Assert.That(samples.Count, Is.GreaterThan(4));
            foreach (var sample in samples)
            {
                double t = (double)sample["t"];
                var players = (JArray)sample["players"];
                Assert.That(players.Count, Is.EqualTo(timeline.Players.Count));
                for (int i = 0; i < players.Count; i++)
                {
                    var player = timeline.Players[i];
                    var expected = players[i].Select(v => (double)v).ToArray();
                    var (x, y) = TimelineSampler.PositionAt(player.Path, t);
                    string at = $"{name}, {player.Role} at {t:0.00}s";
                    Assert.That(x, Is.EqualTo(expected[0]).Within(Tolerance), $"{at}: x");
                    Assert.That(y, Is.EqualTo(expected[1]).Within(Tolerance), $"{at}: y");
                    Assert.That(TimelineSampler.FacingAt(player, t), Is.EqualTo(expected[2]).Within(Tolerance),
                                $"{at}: facing");
                    var angles = TimelineSampler.AnglesAt(player, t);
                    Assert.That(angles.ToArray(), Is.EqualTo(expected.Skip(3).Take(13).ToArray()).Within(Tolerance),
                                $"{at}: joint angles");
                    Assert.That(new Build(player.HeightIn, player.WeightLb).HipHeight(angles),
                                Is.EqualTo(expected[16]).Within(Tolerance), $"{at}: hip height");
                }
                var ball = TimelineSampler.BallAt(timeline, t, id => byId[id]);
                var b = sample["ball"].Select(v => (double)v).ToArray();
                Assert.That(new[] { ball.X, ball.Y, ball.Z }, Is.EqualTo(b).Within(Tolerance), $"{name}: ball at {t:0.00}s");
            }
        }

        [Test]
        public void ThereAreFixturesForRunsPassesAndKicks()
        {
            Assert.That(Cases(), Is.SupersetOf(new[] { "run", "pass", "punt" }));
        }
    }
}
