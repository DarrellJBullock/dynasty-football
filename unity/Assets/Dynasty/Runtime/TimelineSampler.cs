// Sampling a play timeline at a moment: where each player is, which way he faces, how far
// he's lying down, and where the ball is. A port of timeline.ts (positionAt, distanceAt,
// velocityAt, facingAt, ballAt, handsAt and the `lie` of anglesAt); shared fixtures
// (Tests/Fixtures/timelines.json, written by the frontend's tests) keep the two in step.

using System;

namespace Dynasty.Playback
{
    public static class TimelineSampler
    {
        const double BlendTime = 0.18; // seconds a new pose blends in over

        static int Segment(int count, Func<int, double> timeAt, double t)
        {
            int lo = 0, hi = count - 1;
            if (t <= timeAt(0)) return 0;
            if (t >= timeAt(hi)) return hi;
            while (hi - lo > 1)
            {
                int mid = (lo + hi) >> 1;
                if (timeAt(mid) <= t) lo = mid;
                else hi = mid;
            }
            return lo;
        }

        static int PathSegment(PathKey[] path, double t) => Segment(path.Length, i => path[i].T, t);

        static int PoseSegment(PoseKey[] poses, double t) => Segment(poses.Length, i => poses[i].T, t);

        public static (double X, double Y) PositionAt(PathKey[] path, double t)
        {
            int i = PathSegment(path, t);
            var a = path[i];
            if (i + 1 >= path.Length || t <= a.T) return (a.X, a.Y);
            var b = path[i + 1];
            double k = Math.Min(1, (t - a.T) / Math.Max(1e-6, b.T - a.T));
            return (a.X + (b.X - a.X) * k, a.Y + (b.Y - a.Y) * k);
        }

        /// <summary>Yards covered by time <paramref name="t"/> (drives the run cycle).</summary>
        public static double DistanceAt(PathKey[] path, double t)
        {
            double total = 0;
            for (int i = 0; i < path.Length - 1; i++)
            {
                var a = path[i];
                var b = path[i + 1];
                if (t <= a.T) break;
                double full = Hypot(b.X - a.X, b.Y - a.Y);
                double share = t >= b.T ? 1 : (t - a.T) / Math.Max(1e-6, b.T - a.T);
                total += full * share;
            }
            return total;
        }

        /// <summary>Speed (yards/second) and heading (null when standing) at <paramref name="t"/>.</summary>
        public static (double Speed, double? Heading) VelocityAt(PathKey[] path, double t)
        {
            int i = PathSegment(path, t);
            var a = path[i];
            if (i + 1 >= path.Length || t < a.T) return (0, null);
            var b = path[i + 1];
            if (t >= b.T) return (0, null);
            double dx = b.X - a.X, dy = b.Y - a.Y;
            double dist = Hypot(dx, dy);
            if (dist < 0.05) return (0, null);
            return (dist / Math.Max(1e-6, b.T - a.T), Math.Atan2(dy, dx));
        }

        /// <summary>Facing at <paramref name="t"/>: pinned by the pose, else the direction of
        /// travel, else the last movement's.</summary>
        public static double FacingAt(TimelinePlayer player, double t)
        {
            var key = player.Poses[PoseSegment(player.Poses, t)];
            if (key.Face.HasValue) return key.Face.Value;
            var (_, heading) = VelocityAt(player.Path, t);
            if (heading.HasValue) return heading.Value;
            for (int i = PathSegment(player.Path, t); i > 0; i--)
            {
                var a = player.Path[i - 1];
                var b = player.Path[i];
                if (Hypot(b.X - a.X, b.Y - a.Y) > 0.05) return Math.Atan2(b.Y - a.Y, b.X - a.X);
            }
            return player.Facing;
        }

        /// <summary>The joint angles at <paramref name="t"/>: the pose's, run by distance
        /// covered and speed, blending in from the last pose over its first moments.</summary>
        public static JointAngles AnglesAt(TimelinePlayer player, double t)
        {
            int i = PoseSegment(player.Poses, t);
            JointAngles Angles(PoseKey k)
            {
                var (speed, _) = VelocityAt(player.Path, t);
                double progress = k.Span.HasValue && k.Span.Value != 0 ? (t - k.T) / k.Span.Value : 0;
                return Poses.Pose(k.Pose, Poses.RunPhase(DistanceAt(player.Path, t)), progress,
                                  Math.Min(1, speed / 7));
            }
            var current = Angles(player.Poses[i]);
            double since = t - player.Poses[i].T;
            if (i > 0 && since < BlendTime) return JointAngles.Blend(Angles(player.Poses[i - 1]), current, since / BlendTime);
            return current;
        }

        /// <summary>0 standing … 1 lying at <paramref name="t"/>.</summary>
        public static double LieAt(TimelinePlayer player, double t) => AnglesAt(player, t).Lie;

        /// <summary>Where a player's hands hold the ball: at his side, a little in front.</summary>
        public static FieldPoint HandsAt(TimelinePlayer player, double t)
        {
            var (x, y) = PositionAt(player.Path, t);
            double facing = FacingAt(player, t);
            return new FieldPoint(x + Math.Cos(facing) * 0.35, y + Math.Sin(facing) * 0.35,
                                  1.05 - LieAt(player, t) * 0.85);
        }

        /// <summary>The ball's position at <paramref name="t"/>.</summary>
        public static FieldPoint BallAt(PlayTimeline timeline, double t, Func<int, TimelinePlayer> byId)
        {
            var segments = timeline.Ball;
            var current = segments.Find(s => t >= s.From && t < s.To) ?? segments[^1];
            switch (current.Kind)
            {
                case BallKind.Held:
                    return HandsAt(byId(current.Player), Math.Min(t, current.To));
                case BallKind.Rest:
                    return current.At;
                default:
                {
                    double k = Math.Min(1, Math.Max(0, (t - current.From) / Math.Max(1e-6, current.To - current.From)));
                    var a = current.Start;
                    var b = current.End;
                    return new FieldPoint(a.X + (b.X - a.X) * k, a.Y + (b.Y - a.Y) * k,
                                          a.Z + (b.Z - a.Z) * k + 4 * current.Apex * k * (1 - k));
                }
            }
        }

        // Math.hypot without the overflow care (field distances are small), matching JS.
        static double Hypot(double dx, double dy) => Math.Sqrt(dx * dx + dy * dy);
    }
}
