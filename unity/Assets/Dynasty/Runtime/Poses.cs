// Procedural poses: a pose is a set of joint angles (radians) the figure applies to its
// skeleton. A port of frontend/src/components/field/players/poses.ts; the shared fixtures
// check every angle.
//
// Conventions (the figure faces +x, up is +y, its right side is +z, in the browser's scene
// coordinates): hip / shoulder swing forward; knee bends back; elbow folds forward; spread
// raises an arm to the side; torso leans forward; crouch drops the hips (a share of leg
// length); lie goes from 0 standing to 1 lying face down.

using System;

namespace Dynasty.Playback
{
    public struct JointAngles
    {
        public double HipL, HipR, KneeL, KneeR, ShoulderL, ShoulderR, ElbowL, ElbowR, SpreadL, SpreadR,
                      Torso, Crouch, Lie;

        public static readonly JointAngles Zero = new() { SpreadL = 0.08, SpreadR = 0.08 };

        /// <summary>In the fixtures' order (poses.ts's JointAngles fields).</summary>
        public double[] ToArray() => new[]
        {
            HipL, HipR, KneeL, KneeR, ShoulderL, ShoulderR, ElbowL, ElbowR, SpreadL, SpreadR, Torso, Crouch, Lie,
        };

        public static JointAngles Blend(JointAngles a, JointAngles b, double t)
        {
            double k = Math.Min(Math.Max(t, 0), 1);
            double L(double x, double y) => x * (1 - k) + y * k;
            return new JointAngles
            {
                HipL = L(a.HipL, b.HipL), HipR = L(a.HipR, b.HipR), KneeL = L(a.KneeL, b.KneeL),
                KneeR = L(a.KneeR, b.KneeR), ShoulderL = L(a.ShoulderL, b.ShoulderL),
                ShoulderR = L(a.ShoulderR, b.ShoulderR), ElbowL = L(a.ElbowL, b.ElbowL),
                ElbowR = L(a.ElbowR, b.ElbowR), SpreadL = L(a.SpreadL, b.SpreadL),
                SpreadR = L(a.SpreadR, b.SpreadR), Torso = L(a.Torso, b.Torso), Crouch = L(a.Crouch, b.Crouch),
                Lie = L(a.Lie, b.Lie),
            };
        }
    }

    /// <summary>Figure proportions in yards, from a player's height and weight.</summary>
    public readonly struct Build
    {
        public readonly double Height, Bulk, Thigh, Shin, Torso, Head, UpperArm, Forearm;

        public Build(double heightIn, double weightLb)
        {
            Height = heightIn / 36;
            double bmi = weightLb / (heightIn * heightIn) * 703; // ~25 receivers, ~40 linemen
            Bulk = Math.Min(1.45, Math.Max(0.85, 0.5 + bmi / 50));
            Thigh = Height * 0.245;
            Shin = Height * 0.235;
            Torso = Height * 0.3;
            Head = Height * 0.13;
            UpperArm = Height * 0.17;
            Forearm = Height * 0.16;
        }

        /// <summary>How high the hips sit for a pose, so the planted foot stays on the ground.</summary>
        public double HipHeight(JointAngles a)
        {
            double thigh = Thigh, shin = Shin;
            double Leg(double hip, double knee) => thigh * Math.Cos(hip) + shin * Math.Cos(hip - knee);
            double standing = Math.Max(Leg(a.HipL, a.KneeL), Leg(a.HipR, a.KneeR));
            return Math.Max(0.15, standing * (1 - a.Lie * 0.75));
        }
    }

    public static class Poses
    {
        /// <summary>Stride length in yards at full speed (a run cycle covers two strides).</summary>
        public const double Stride = 2.1;

        public static double RunPhase(double distance) => distance / (2 * Stride) * Math.PI * 2;

        /// <summary>The joint angles of a pose: <paramref name="phase"/> through the run
        /// cycle, <paramref name="progress"/> through a one-off motion (0–1), and
        /// <paramref name="effort"/> (0–1) of running.</summary>
        public static JointAngles Pose(string name, double phase = 0, double progress = 0, double effort = 1)
        {
            var a = JointAngles.Zero;
            switch (name)
            {
                case "stand":
                    a.ElbowL = 0.2; a.ElbowR = 0.2;
                    return a;
                case "stance3":
                    a.HipL = 1.35; a.HipR = 1.15; a.KneeL = 1.7; a.KneeR = 1.4; a.Torso = 1.15; a.Crouch = 0.42;
                    a.ShoulderR = 1.35; a.ElbowR = 0.05; a.ShoulderL = 0.95; a.ElbowL = 1.3;
                    return a;
                case "stance2":
                    a.HipL = 0.55; a.HipR = 0.45; a.KneeL = 0.8; a.KneeR = 0.7; a.Torso = 0.45; a.Crouch = 0.16;
                    a.ShoulderL = 0.75; a.ShoulderR = 0.75; a.ElbowL = 0.2; a.ElbowR = 0.2;
                    return a;
                case "run":
                case "carry":
                {
                    double s = Math.Sin(phase);
                    double legs = 0.75 * effort + 0.15;
                    a.HipL = legs * s; a.HipR = -legs * s;
                    a.KneeL = 0.25 + 1.1 * Math.Max(0, -Math.Sin(phase - 0.6)) * effort;
                    a.KneeR = 0.25 + 1.1 * Math.Max(0, Math.Sin(phase - 0.6)) * effort;
                    a.Torso = 0.12 + 0.2 * effort;
                    a.ElbowL = 1.4; a.ElbowR = 1.4;
                    a.Crouch = 0.05 + 0.04 * Math.Abs(Math.Cos(phase));
                    a.ShoulderL = a.Torso - 0.8 * effort * s; // arms swing opposite the legs
                    a.ShoulderR = a.Torso + 0.8 * effort * s;
                    if (name == "carry")
                    {
                        a.ShoulderR = a.Torso + 0.35; // ball tucked under the right arm
                        a.ElbowR = 1.9;
                    }
                    return a;
                }
                case "block":
                    a.HipL = 0.9; a.HipR = 0.3; a.KneeL = 1.0; a.KneeR = 0.6; a.Torso = 0.6; a.Crouch = 0.2;
                    a.ShoulderL = 1.9; a.ShoulderR = 1.9; a.ElbowL = 0.35; a.ElbowR = 0.35;
                    return a;
                case "throw":
                {
                    double p = Math.Min(Math.Max(progress, 0), 1);
                    double release = p < 0.6 ? -2.4 * (p / 0.6) : -2.4 + 3.8 * ((p - 0.6) / 0.4);
                    a.HipL = 0.35; a.HipR = -0.25; a.KneeL = 0.3; a.KneeR = 0.2; a.Torso = 0.1 + 0.25 * p;
                    a.Crouch = 0.06; a.ShoulderR = release; a.ElbowR = p < 0.6 ? 1.6 : 1.6 - 1.4 * ((p - 0.6) / 0.4);
                    a.ShoulderL = 0.9 - 0.6 * p; a.ElbowL = 0.8; a.SpreadR = 0.4;
                    return a;
                }
                case "catch":
                    a.HipL = 0.2; a.KneeL = 0.2; a.KneeR = 0.15; a.Torso = -0.05;
                    a.ShoulderL = 2.5; a.ShoulderR = 2.5; a.ElbowL = 0.25; a.ElbowR = 0.25; a.SpreadL = 0.2; a.SpreadR = 0.2;
                    return a;
                case "dive":
                    a.HipL = -0.35; a.HipR = -0.5; a.KneeL = 0.4; a.KneeR = 0.6; a.Torso = 1.35; a.Crouch = 0.5;
                    a.ShoulderL = 2.9; a.ShoulderR = 2.9; a.ElbowL = 0.5; a.ElbowR = 0.5; a.Lie = 0.35;
                    return a;
                case "down":
                    a.HipL = 0.1; a.KneeL = 0.3; a.KneeR = 0.1; a.ShoulderL = 0.4; a.ShoulderR = 2.6;
                    a.ElbowL = 0.6; a.ElbowR = 0.4; a.Lie = 1;
                    return a;
                case "kneel":
                    a.HipL = 1.45; a.KneeL = 1.5; a.HipR = -0.1; a.KneeR = 1.55; a.Torso = 0.1;
                    a.ShoulderL = 0.5; a.ShoulderR = 0.4; a.ElbowL = 0.9; a.ElbowR = 0.9;
                    return a;
                case "kick":
                {
                    double p = Math.Min(Math.Max(progress, 0), 1);
                    a.HipL = 0.15; a.KneeL = 0.35; a.HipR = -0.7 + 2.5 * p; a.KneeR = 1.3 * (1 - p);
                    a.Torso = 0.15 - 0.3 * p; a.Crouch = 0.05; a.ShoulderL = 0.9; a.ShoulderR = -0.3;
                    a.SpreadL = 0.7; a.SpreadR = 0.5; a.ElbowL = 0.3; a.ElbowR = 0.3;
                    return a;
                }
                case "celebrate":
                    a.ShoulderL = 2.9; a.ShoulderR = 2.9; a.ElbowL = 0.15; a.ElbowR = 0.15; a.SpreadL = 0.35; a.SpreadR = 0.35;
                    return a;
                default:
                    return a;
            }
        }
    }
}
