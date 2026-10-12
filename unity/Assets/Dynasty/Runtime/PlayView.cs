// One play on the field: a figure for each of the 22 players in his team's colors, the
// ball and the flag, posed from the timeline at the playhead. The foundation's figures are
// simple capsules; the animated athletes come in Milestone 9, part 4.

using System.Collections.Generic;
using UnityEngine;

namespace Dynasty.Playback
{
    public sealed class PlayView
    {
        const float YardsPerInch = 1f / 36f;

        readonly Transform root;
        readonly Material lit;
        readonly List<(TimelinePlayer Player, Transform Figure)> figures = new();
        readonly Dictionary<int, TimelinePlayer> byId = new();
        Transform ball;
        Transform flag;

        public PlayTimeline Timeline { get; private set; }

        public PlayView(Transform parent)
        {
            root = new GameObject("Play").transform;
            root.SetParent(parent, false);
            lit = new Material(Resources.Load<Material>("Lit"));
        }

        public int FigureCount => figures.Count;

        public void Load(PlayTimeline timeline, IReadOnlyDictionary<int, Color> teamColors)
        {
            foreach (Transform child in root) Object.Destroy(child.gameObject);
            figures.Clear();
            byId.Clear();
            Timeline = timeline;
            foreach (var player in timeline.Players)
            {
                byId[player.Id] = player;
                var color = teamColors.TryGetValue(player.TeamId, out var c) ? c : Color.gray;
                figures.Add((player, Figure(player, color)));
            }
            ball = Shape(PrimitiveType.Sphere, "Ball", new Vector3(0.25f, 0.18f, 0.18f),
                         new Color(0.45f, 0.24f, 0.1f));
            flag = Shape(PrimitiveType.Cube, "Flag", new Vector3(0.4f, 0.02f, 0.4f), new Color(0.98f, 0.8f, 0.08f));
            flag.gameObject.SetActive(false);
        }

        Transform Shape(PrimitiveType type, string name, Vector3 scale, Color color)
        {
            var shape = GameObject.CreatePrimitive(type);
            Object.Destroy(shape.GetComponent<Collider>());
            shape.name = name;
            shape.transform.SetParent(root, false);
            shape.transform.localScale = scale;
            var renderer = shape.GetComponent<Renderer>();
            renderer.sharedMaterial = lit;
            renderer.material.color = color;
            return shape.transform;
        }

        Transform Figure(TimelinePlayer player, Color color)
        {
            float height = (float)player.HeightIn * YardsPerInch;
            float bulk = Mathf.Clamp((float)player.WeightLb / 230f, 0.8f, 1.4f);
            var figure = new GameObject($"{player.Side} {player.Role}").transform;
            figure.SetParent(root, false);
            // The body stands on the figure's origin; the figure turns to face and tips over to lie.
            var body = Shape(PrimitiveType.Capsule, "Body", new Vector3(0.55f * bulk, height / 2, 0.45f * bulk), color);
            body.SetParent(figure, false);
            body.localPosition = new Vector3(0, height / 2, 0);
            var nose = Shape(PrimitiveType.Cube, "Facing", new Vector3(0.12f, 0.12f, 0.3f), Color.white);
            nose.SetParent(figure, false);
            nose.localPosition = new Vector3(0, height * 0.85f, 0.25f * bulk);
            return figure;
        }

        /// <summary>Everything as it is at <paramref name="t"/> seconds into the play.</summary>
        public void Show(double t)
        {
            if (Timeline == null) return;
            foreach (var (player, figure) in figures)
            {
                var (x, y) = TimelineSampler.PositionAt(player.Path, t);
                figure.localPosition = Field.ToWorld(x, y);
                double lie = TimelineSampler.LieAt(player, t);
                figure.localRotation = Field.Facing(TimelineSampler.FacingAt(player, t))
                                       * Quaternion.Euler((float)lie * 90f * 0.95f, 0, 0);
            }
            ball.localPosition = Field.ToWorld(TimelineSampler.BallAt(Timeline, t, id => byId[id]));
            var thrown = Timeline.Flag;
            flag.gameObject.SetActive(thrown != null && t >= thrown.T);
            if (thrown != null && t >= thrown.T)
            {
                double k = System.Math.Min(1, (t - thrown.T) / 0.7);
                flag.localPosition = Field.ToWorld(thrown.X, Mathf.Clamp((float)thrown.Y, 0, Field.Width),
                                                   2.4 * (1 - k * k) + 0.02);
            }
        }
    }
}
