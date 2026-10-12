// Field geometry and the coordinate mapping shared with the browser's viewer (layout.ts).
//
// Field coordinates are yards: x along (0-120, goal lines at 10 and 110), y across
// (0-53.3), z up. The browser's three.js scene puts midfield at the origin with +Y up:
// scene (x − 60, z, y − 26.67). Unity is left-handed, so its Z is the scene's flipped.

using System;
using System.Globalization;
using UnityEngine;

namespace Dynasty.Playback
{
    public static class Field
    {
        public const float Length = 120f;
        public const float Width = 160f / 3f;
        public const float EndZone = 10f;

        /// <summary>A field point in Unity world space.</summary>
        public static Vector3 ToWorld(double x, double y, double z = 0) =>
            new((float)(x - Length / 2), (float)z, -(float)(y - Width / 2));

        public static Vector3 ToWorld(FieldPoint p) => ToWorld(p.X, p.Y, p.Z);

        /// <summary>A point in the browser's three.js scene coordinates, in Unity world space.</summary>
        public static Vector3 FromScene(double x, double y, double z) =>
            new((float)x, (float)y, -(float)z);

        /// <summary>The world rotation for a facing (radians, from +x toward +y on the field).</summary>
        public static Quaternion Facing(double facing) =>
            Quaternion.LookRotation(new Vector3((float)Math.Cos(facing), 0, -(float)Math.Sin(facing)));
    }

    /// <summary>One frame from the browser: the playhead and the camera (three.js scene
    /// coordinates), sent as "t,px,py,pz,tx,ty,tz,fov".</summary>
    public readonly struct Frame
    {
        public readonly double Time;
        public readonly Vector3 Position;
        public readonly Vector3 Target;
        public readonly float Fov;

        public Frame(double time, Vector3 position, Vector3 target, float fov)
        {
            Time = time;
            Position = position;
            Target = target;
            Fov = fov;
        }

        public static Frame Parse(string message)
        {
            var parts = message.Split(',');
            if (parts.Length != 8) throw new FormatException($"A frame has 8 numbers, not {parts.Length}.");
            var n = Array.ConvertAll(parts, s => double.Parse(s, NumberStyles.Float, CultureInfo.InvariantCulture));
            return new Frame(n[0], Field.FromScene(n[1], n[2], n[3]), Field.FromScene(n[4], n[5], n[6]),
                             (float)n[7]);
        }
    }
}
