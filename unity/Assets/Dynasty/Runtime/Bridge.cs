// The bridge to the web page (docs/design/depth-and-unity.md §4.1). The page sends:
//   LoadPlay(json)  {"timeline": PlayTimeline, "teams": {"<id>": "#rrggbb"}, "endZone": "#rrggbb"}
//   SetFrame(csv)   "t,px,py,pz,tx,ty,tz,fov": the playhead, and the camera in three.js
//                   scene coordinates (the page's director and camera rig decide the shot)
// and hears back through DynastyBridge.jslib: "ready" once the stage is built, "loaded"
// with the number of figures, and "error" with a message. Unity only draws: the browser
// owns the clock, the cameras, replays and the broadcast graphics.

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Dynasty.Playback
{
    public sealed class Bridge : MonoBehaviour
    {
        Stage stage;
        PlayView view;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (FindAnyObjectByType<Bridge>() == null) new GameObject("Bridge").AddComponent<Bridge>();
        }

        void Start()
        {
            Application.targetFrameRate = -1;
            stage = new Stage(transform);
            view = new PlayView(transform);
            Notify("ready", "");
        }

        /// <summary>A new play: its timeline and the teams' colors.</summary>
        public void LoadPlay(string json)
        {
            try
            {
                var message = Message.Parse(json);
                view.Load(message.Timeline, message.TeamColors);
                stage.Mark(message.Timeline.Los, message.Timeline.FirstDownLine);
                if (message.EndZone.HasValue) stage.Paint(message.EndZone.Value);
                view.Show(0);
                Notify("loaded", view.FigureCount.ToString());
            }
            catch (Exception e)
            {
                Notify("error", $"LoadPlay: {e.Message}");
            }
        }

        /// <summary>The playhead and the camera for this frame.</summary>
        public void SetFrame(string csv)
        {
            try
            {
                var frame = Frame.Parse(csv);
                stage.Aim(frame);
                view.Show(frame.Time);
            }
            catch (Exception e)
            {
                Notify("error", $"SetFrame: {e.Message}");
            }
        }

        public readonly struct Message
        {
            public readonly PlayTimeline Timeline;
            public readonly Dictionary<int, Color> TeamColors;
            public readonly Color? EndZone;

            Message(PlayTimeline timeline, Dictionary<int, Color> teamColors, Color? endZone)
            {
                Timeline = timeline;
                TeamColors = teamColors;
                EndZone = endZone;
            }

            public static Message Parse(string json)
            {
                var o = JObject.Parse(json);
                var colors = new Dictionary<int, Color>();
                if (o["teams"] is JObject teams)
                {
                    foreach (var team in teams.Properties())
                    {
                        if (int.TryParse(team.Name, out int id) && ColorUtility.TryParseHtmlString((string)team.Value, out var c))
                            colors[id] = c;
                    }
                }
                Color? endZone = ColorUtility.TryParseHtmlString((string)o["endZone"] ?? "", out var z) ? z : null;
                return new Message(PlayTimeline.FromJson((JObject)o["timeline"]), colors, endZone);
            }
        }

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        static extern void DynastyNotify(string type, string detail);
#else
        static void DynastyNotify(string type, string detail) => Debug.Log($"[bridge] {type} {detail}");
#endif

        static void Notify(string type, string detail) => DynastyNotify(type, detail);
    }
}
