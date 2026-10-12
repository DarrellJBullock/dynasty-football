// The page's messages (Bridge.cs) and the coordinate mapping shared with layout.ts.

using System;
using Dynasty.Playback;
using NUnit.Framework;
using UnityEngine;

namespace Dynasty.Tests
{
    public class BridgeTests
    {
        const string Timeline = @"{""duration"": 4, ""direction"": -1, ""los"": 60, ""firstDownLine"": null,
            ""players"": [{""id"": 7, ""side"": ""offense"", ""teamId"": 3, ""role"": ""QB"", ""name"": ""K. Quarles"",
                ""number"": 15, ""position"": ""QB"", ""heightIn"": 75, ""weightLb"": 220, ""facing"": 3.14,
                ""path"": [{""t"": 0, ""x"": 61, ""y"": 26}], ""poses"": [{""t"": 0, ""pose"": ""stance2""}]}],
            ""ball"": [{""kind"": ""held"", ""from"": 0, ""to"": 2, ""player"": 7},
                       {""kind"": ""flight"", ""from"": 2, ""to"": 3, ""start"": [60, 26, 2], ""end"": [40, 20, 1], ""apex"": 3},
                       {""kind"": ""rest"", ""from"": 3, ""to"": 4, ""at"": [40, 20, 0.1]}],
            ""moments"": [{""t"": 1, ""kind"": ""snap"", ""text"": ""Snap""}], ""flag"": null}";

        [Test]
        public void ParsesALoadPlayMessage()
        {
            var message = Bridge.Message.Parse(
                $@"{{""timeline"": {Timeline}, ""kits"": {{
                    ""3"": {{""jersey"": ""#ff0000"", ""numbers"": ""#ffffff"", ""pants"": ""#0000ff"",
                             ""helmet"": ""nonsense"", ""socks"": ""#ff0000""}},
                    ""x"": {{""jersey"": ""#000000""}}}}}}");
            var timeline = message.Timeline;
            Assert.That((timeline.Duration, timeline.Direction, timeline.Los, timeline.FirstDownLine),
                        Is.EqualTo((4.0, -1, (double?)60, (double?)null)));
            Assert.That(timeline.Players[0].Name, Is.EqualTo("K. Quarles"));
            Assert.That(timeline.Ball.ConvertAll(s => s.Kind),
                        Is.EqualTo(new[] { BallKind.Held, BallKind.Flight, BallKind.Rest }));
            Assert.That(timeline.Ball[1].Apex, Is.EqualTo(3));
            Assert.That(timeline.Flag, Is.Null);
            Assert.That(message.Kits, Has.Count.EqualTo(1)); // the bad team id is skipped
            var kit = message.Kits[3];
            Assert.That((kit.Jersey, kit.Numbers, kit.Pants, kit.Socks),
                        Is.EqualTo((Color.red, Color.white, Color.blue, Color.red)));
            Assert.That(kit.Helmet, Is.EqualTo(Color.gray)); // a bad color falls back
        }

        [Test]
        public void ParsesAFrame()
        {
            var frame = Frame.Parse("1.25,10,20,30,-4,0,2.5,26");
            Assert.That(frame.Time, Is.EqualTo(1.25));
            Assert.That(frame.Position, Is.EqualTo(new Vector3(10, 20, -30))); // three.js → Unity
            Assert.That(frame.Target, Is.EqualTo(new Vector3(-4, 0, -2.5f)));
            Assert.That(frame.Fov, Is.EqualTo(26));
            Assert.Throws<FormatException>(() => Frame.Parse("1,2,3"));
        }

        [Test]
        public void SkinTonesMatchTheBrowser()
        {
            // kit.ts skinTone: SKIN[|imul(id, 2654435761)| % 7] (values from the browser).
            Assert.That(Kit.SkinTone(1), Is.EqualTo("#4a2a17"));
            Assert.That(Kit.SkinTone(3), Is.EqualTo("#f1c9a5"));
            Assert.That(Kit.SkinTone(7), Is.EqualTo("#6b3e1f"));
            Assert.That(Kit.SkinTone(1234), Is.EqualTo("#8d5524"));
            Assert.That(Kit.SkinTone(-1012), Is.EqualTo("#6b3e1f"));
        }

        [Test]
        public void ProportionsComeFromHeightAndWeight()
        {
            var lineman = new Build(77, 320);
            var receiver = new Build(72, 190);
            Assert.That(lineman.Height, Is.EqualTo(77 / 36.0).Within(1e-9));
            Assert.That(lineman.Bulk, Is.GreaterThan(receiver.Bulk));
            Assert.That(new Build(70, 600).Bulk, Is.EqualTo(1.45)); // capped
            Assert.That(lineman.HipHeight(JointAngles.Zero), Is.EqualTo(lineman.Thigh + lineman.Shin).Within(1e-9));
        }

        static void Near(Vector3 actual, Vector3 expected) =>
            Assert.That((actual - expected).magnitude, Is.LessThan(1e-4f), $"{actual} vs {expected}");

        [Test]
        public void MapsTheFieldLikeTheBrowser()
        {
            // layout.ts toScene(x, y, z) = [x − 60, z, y − 26.67]; Unity flips the scene's Z.
            Near(Field.ToWorld(60, Field.Width / 2), Vector3.zero);
            Near(Field.ToWorld(110, 0, 3), new Vector3(50, 3, Field.Width / 2));
            // Facing +x on the field looks along +X; facing +y (across) looks toward −Z.
            Near(Field.Facing(0) * Vector3.forward, Vector3.right);
            Near(Field.Facing(Math.PI / 2) * Vector3.forward, Vector3.back);
        }
    }
}
