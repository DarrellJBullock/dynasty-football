// Command-line entry points (make unity-build / CI):
//   Unity -batchmode -quit -projectPath unity -executeMethod Dynasty.BuildScript.BuildWebGL
//         [-buildOutput ../frontend/public/unity]
// The build lands in <output>/Build/, with <output>/build.json naming its files for the
// page (frontend/src/lib/unity.ts). Setup() creates the few assets the runtime loads.

using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Dynasty
{
    public static class BuildScript
    {
        const string ScenePath = "Assets/Scenes/Main.unity";
        const string Resources = "Assets/Dynasty/Resources";

        /// <summary>The materials (in Resources, so their shaders ship) and the one scene; the
        /// Bridge builds everything else at runtime.</summary>
        public static void Setup()
        {
            Directory.CreateDirectory(Resources);
            EnsureMaterial("Lit", "Standard");
            EnsureMaterial("Line", "Unlit/Color");
            EnsureMaterial("Crowd", "Dynasty/VertexColorLit");
            // The light towers' lamps glow: a material asset with emission on, so the
            // Standard shader's emissive variant is kept in the build.
            if (EnsureMaterial("Lamps", "Standard") is { } lamps)
            {
                lamps.color = new Color(0.97f, 0.98f, 0.99f);
                lamps.EnableKeyword("_EMISSION");
                lamps.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
                lamps.SetColor("_EmissionColor", new Color(1f, 0.97f, 0.84f) * 1.4f);
                EditorUtility.SetDirty(lamps);
            }
            // (Jersey numbers use the runtime's built-in font, which ships with its own shader.)
            if (!File.Exists(ScenePath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                EditorSceneManager.SaveScene(scene, ScenePath);
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            AssetDatabase.SaveAssets();
        }

        /// <summary>Creates the material if it's missing (returning it), else null.</summary>
        static Material EnsureMaterial(string name, string shader)
        {
            string path = $"{Resources}/{name}.mat";
            if (AssetDatabase.LoadAssetAtPath<Material>(path) != null) return null;
            var found = Shader.Find(shader) ?? throw new InvalidOperationException($"No shader {shader}.");
            var material = new Material(found);
            AssetDatabase.CreateAsset(material, path);
            return material;
        }

        public static void BuildWebGL()
        {
            Setup();
            string output = Argument("-buildOutput") ?? Path.GetFullPath("../frontend/public/unity");
            if (Directory.Exists(output)) Directory.Delete(output, true);

            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
            // Decompress in the loader when the server doesn't send Content-Encoding (Next's
            // static files don't), so no special headers are needed anywhere.
            PlayerSettings.WebGL.decompressionFallback = true;
            PlayerSettings.WebGL.dataCaching = true;
            PlayerSettings.SetManagedStrippingLevel(UnityEditor.Build.NamedBuildTarget.WebGL,
                                                    ManagedStrippingLevel.Medium);
            PlayerSettings.runInBackground = true;

            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = output,
                target = BuildTarget.WebGL,
                options = BuildOptions.None,
            });
            if (report.summary.result != BuildResult.Succeeded)
            {
                Debug.LogError($"WebGL build failed: {report.summary.result}");
                EditorApplication.Exit(1);
                return;
            }
            WriteManifest(output);
            Debug.Log($"WebGL build: {output} ({report.summary.totalSize / 1024 / 1024} MB)");
        }

        /// <summary>build.json: the loader, data, framework and code files the page passes to
        /// createUnityInstance (names depend on the compression settings).</summary>
        static void WriteManifest(string output)
        {
            var files = Directory.GetFiles(Path.Combine(output, "Build")).Select(Path.GetFileName).ToArray();
            string Find(string marker) =>
                files.FirstOrDefault(f => f.Contains(marker)) ?? throw new FileNotFoundException(marker);
            var manifest = "{\n" +
                           $"  \"loader\": \"Build/{Find(".loader.js")}\",\n" +
                           $"  \"data\": \"Build/{Find(".data")}\",\n" +
                           $"  \"framework\": \"Build/{Find(".framework.js")}\",\n" +
                           $"  \"code\": \"Build/{Find(".wasm")}\",\n" +
                           $"  \"unity\": \"{Application.unityVersion}\"\n" +
                           "}\n";
            File.WriteAllText(Path.Combine(output, "build.json"), manifest);
            // (Unity's own page and template files aren't used: the app embeds the canvas.)
            foreach (var extra in new[] { "index.html", "TemplateData" })
            {
                string path = Path.Combine(output, extra);
                if (File.Exists(path)) File.Delete(path);
                if (Directory.Exists(path)) Directory.Delete(path, true);
            }
        }

        static string Argument(string name)
        {
            var args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }
    }
}
