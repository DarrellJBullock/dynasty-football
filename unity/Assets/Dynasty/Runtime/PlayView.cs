// One play on the field: an athlete for each of the 22 players in his team's uniform, the
// football and the penalty flag, posed from the timeline at the playhead (as the browser's
// PlayScene.tsx does). Built under the stage's mirrored root, in scene coordinates.

using System.Collections.Generic;
using UnityEngine;

namespace Dynasty.Playback
{
    public sealed class PlayView
    {
        readonly Transform root;
        readonly Font font;
        readonly List<(TimelinePlayer Player, Athlete Athlete)> athletes = new();
        readonly Dictionary<int, TimelinePlayer> byId = new();
        Transform ball;
        Transform flag;

        public PlayTimeline Timeline { get; private set; }

        public PlayView(Transform scene)
        {
            root = Parts.Group(scene, "Play");
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }

        public int FigureCount => athletes.Count;

        public void Load(PlayTimeline timeline, IReadOnlyDictionary<int, Kit> kits)
        {
            for (int i = root.childCount - 1; i >= 0; i--) Parts.Remove(root.GetChild(i).gameObject);
            athletes.Clear();
            byId.Clear();
            Timeline = timeline;
            foreach (var player in timeline.Players)
            {
                byId[player.Id] = player;
                var kit = kits.TryGetValue(player.TeamId, out var k) ? k : Kit.Plain;
                athletes.Add((player, new Athlete(root, player, kit, font)));
            }
            ball = Football();
            flag = Parts.Group(root, "Flag");
            Parts.Box(flag, "Cloth", Vector3.zero, new Vector3(0.4f, 0.02f, 0.4f), Parts.Lit(Parts.Hex("#facc15"), 0.8f));
            flag.gameObject.SetActive(false);
        }

        Transform Football()
        {
            var football = Parts.Group(root, "Football");
            var leather = Parts.Lit(Parts.Hex("#7a3e16"), 0.6f);
            var body = Parts.Sphere(football, "Ball", Vector3.zero, 1, leather);
            body.localScale = new Vector3(0.31f, 0.19f, 0.19f); // a prolate spheroid
            Parts.Box(football, "Laces", new Vector3(0, 0.093f, 0), new Vector3(0.06f, 0.006f, 0.012f),
                      Parts.Lit(Parts.Hex("#f8fafc"), 0.6f));
            return football;
        }

        /// <summary>Everything as it is at <paramref name="t"/> seconds into the play.</summary>
        public void Show(double t)
        {
            if (Timeline == null) return;
            foreach (var (player, athlete) in athletes)
            {
                var (x, y) = TimelineSampler.PositionAt(player.Path, t);
                athlete.Pose(x, y, TimelineSampler.FacingAt(player, t), TimelineSampler.AnglesAt(player, t));
            }
            var at = TimelineSampler.BallAt(Timeline, t, id => byId[id]);
            ball.localPosition = Field.ToScene(at);
            bool flying = Timeline.Ball.Exists(s => s.Kind == BallKind.Flight && t >= s.From && t < s.To);
            ball.localRotation = Quaternion.Euler(flying ? Parts.Deg(t * 25) : 0, 0, 0);

            var thrown = Timeline.Flag;
            bool down = thrown != null && t >= thrown.T;
            flag.gameObject.SetActive(down);
            if (down)
            {
                double since = t - thrown.T;
                double k = System.Math.Min(1, since / 0.7);
                var spot = Field.ToScene(thrown.X, Mathf.Clamp((float)thrown.Y, 0, Field.Width));
                flag.localPosition = new Vector3(spot.x, (float)(2.4 * (1 - k * k) + 0.02), spot.z);
                // (three.js's Euler order: X, then Y.)
                flag.localRotation = Quaternion.Euler(Parts.Deg(System.Math.Sin(since * 9) * 0.6 * (1 - k)), 0, 0)
                                     * Quaternion.Euler(0, Parts.Deg(since * 3 * (1 - k)), 0);
            }
        }
    }
}
