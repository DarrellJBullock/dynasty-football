// The play timeline (docs/design/play-playback.md §3), as the browser's choreographer
// builds it (frontend/src/components/field/playback/timeline.ts): every player's path and
// poses over time, the ball, the moments and the flag. Field coordinates in yards: x along
// the field (0-120, goal lines at 10 and 110), y across it (0-53.3), z up.

using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace Dynasty.Playback
{
    public struct PathKey
    {
        public double T, X, Y;
    }

    public struct PoseKey
    {
        public double T;
        public string Pose;
        public double? Span; // times one-off motions (a throw, a kick)
        public double? Face; // pins the facing (radians) instead of following the motion
    }

    /// <summary>A point in field coordinates (yards): x along, y across, z up.</summary>
    public struct FieldPoint
    {
        public double X, Y, Z;

        public FieldPoint(double x, double y, double z)
        {
            X = x;
            Y = y;
            Z = z;
        }
    }

    public sealed class TimelinePlayer
    {
        public int Id; // negative: not a named player (kick units, stand-ins)
        public string Side; // "offense" | "defense"
        public int TeamId;
        public string Role;
        public string Name;
        public int Number;
        public string Position;
        public double HeightIn;
        public double WeightLb;
        public double Facing; // at the start
        public PathKey[] Path;
        public PoseKey[] Poses;
    }

    public enum BallKind
    {
        Held,
        Flight,
        Rest,
    }

    public sealed class BallSegment
    {
        public BallKind Kind;
        public double From, To;
        public int Player; // held
        public FieldPoint Start, End; // flight
        public double Apex; // flight
        public FieldPoint At; // rest
    }

    public sealed class Moment
    {
        public double T;
        public string Kind;
        public string Text;
    }

    public sealed class PenaltyFlag
    {
        public double T, X, Y;
    }

    public sealed class PlayTimeline
    {
        public double Duration;
        public int Direction; // the offense drives toward +x (1) or −x (−1)
        public double? Los;
        public double? FirstDownLine;
        public List<TimelinePlayer> Players = new();
        public List<BallSegment> Ball = new();
        public List<Moment> Moments = new();
        public PenaltyFlag Flag;

        public static PlayTimeline Parse(string json) => FromJson(JObject.Parse(json));

        public static PlayTimeline FromJson(JObject o)
        {
            var timeline = new PlayTimeline
            {
                Duration = (double)o["duration"],
                Direction = (int)o["direction"],
                Los = (double?)o["los"],
                FirstDownLine = (double?)o["firstDownLine"],
            };
            foreach (var p in o["players"])
            {
                timeline.Players.Add(new TimelinePlayer
                {
                    Id = (int)p["id"],
                    Side = (string)p["side"],
                    TeamId = (int)p["teamId"],
                    Role = (string)p["role"],
                    Name = (string)p["name"],
                    Number = (int)p["number"],
                    Position = (string)p["position"],
                    HeightIn = (double)p["heightIn"],
                    WeightLb = (double)p["weightLb"],
                    Facing = (double)p["facing"],
                    Path = p["path"].Select(k => new PathKey
                    {
                        T = (double)k["t"], X = (double)k["x"], Y = (double)k["y"],
                    }).ToArray(),
                    Poses = p["poses"].Select(k => new PoseKey
                    {
                        T = (double)k["t"],
                        Pose = (string)k["pose"],
                        Span = (double?)k["span"],
                        Face = (double?)k["face"],
                    }).ToArray(),
                });
            }
            foreach (var s in o["ball"])
            {
                var segment = new BallSegment { From = (double)s["from"], To = (double)s["to"] };
                switch ((string)s["kind"])
                {
                    case "held":
                        segment.Kind = BallKind.Held;
                        segment.Player = (int)s["player"];
                        break;
                    case "flight":
                        segment.Kind = BallKind.Flight;
                        segment.Start = Point(s["start"]);
                        segment.End = Point(s["end"]);
                        segment.Apex = (double)s["apex"];
                        break;
                    default:
                        segment.Kind = BallKind.Rest;
                        segment.At = Point(s["at"]);
                        break;
                }
                timeline.Ball.Add(segment);
            }
            foreach (var m in o["moments"] ?? new JArray())
            {
                timeline.Moments.Add(new Moment
                {
                    T = (double)m["t"], Kind = (string)m["kind"], Text = (string)m["text"],
                });
            }
            var flag = o["flag"];
            if (flag != null && flag.Type == JTokenType.Object)
            {
                timeline.Flag = new PenaltyFlag
                {
                    T = (double)flag["t"], X = (double)flag["x"], Y = (double)flag["y"],
                };
            }
            return timeline;
        }

        static FieldPoint Point(JToken a) => new((double)a[0], (double)a[1], (double)a[2]);
    }
}
