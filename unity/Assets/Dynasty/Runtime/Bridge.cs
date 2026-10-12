// The bridge to the web page (docs/design/depth-and-unity.md §4.1; docs/unity.md). The
// page sends:
//   SetField(json)  {"image": "<base64 PNG>", "crowd": ["#home", "#colors"]}: the field as
//                   the page paints it (fieldTexture.ts), and the home fans' colors
//   LoadPlay(json)  {"timeline": PlayTimeline, "kits": {"<team id>": {"jersey", "numbers",
//                   "pants", "helmet", "socks"}}}
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
            view = new PlayView(stage.Scene);
            Notify("ready", "");
        }

        /// <summary>The field and the crowd, once per game.</summary>
        public void SetField(string json)
        {
            try
            {
                var o = JObject.Parse(json);
                stage.Paint(Convert.FromBase64String((string)o["image"]));
                if (o["crowd"] is JArray crowd && crowd.Count > 0)
                    stage.Crowd(Array.ConvertAll(crowd.ToObject<string[]>(), c => Parts.Hex(c, Color.gray)));
            }
            catch (Exception e)
            {
                Notify("error", $"SetField: {e.Message}");
            }
        }

        /// <summary>A new play: its timeline and the teams' uniforms.</summary>
        public void LoadPlay(string json)
        {
            try
            {
                var message = Message.Parse(json);
                view.Load(message.Timeline, message.Kits);
                stage.Mark(message.Timeline.Los, message.Timeline.FirstDownLine);
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
            public readonly Dictionary<int, Kit> Kits;

            Message(PlayTimeline timeline, Dictionary<int, Kit> kits)
            {
                Timeline = timeline;
                Kits = kits;
            }

            public static Message Parse(string json)
            {
                var o = JObject.Parse(json);
                var kits = new Dictionary<int, Kit>();
                if (o["kits"] is JObject teams)
                {
                    foreach (var team in teams.Properties())
                    {
                        if (!int.TryParse(team.Name, out int id) || team.Value is not JObject k) continue;
                        Color C(string key) => Parts.Hex((string)k[key], Color.gray);
                        kits[id] = new Kit(C("jersey"), C("numbers"), C("pants"), C("helmet"), C("socks"));
                    }
                }
                return new Message(PlayTimeline.FromJson((JObject)o["timeline"]), kits);
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
