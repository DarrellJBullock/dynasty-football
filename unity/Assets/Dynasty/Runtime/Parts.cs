// Building blocks for figures and the stadium, sized like the browser's three.js shapes
// (capsule radius/length, cylinder radii/height, sphere radius, box size), so the Unity
// models can be built from the same numbers. Everything is placed in the browser's scene
// coordinates under the mirrored root (Stage.cs), where Unity's Euler rotations match
// three.js's numerically for the axes used.

using UnityEngine;

namespace Dynasty.Playback
{
    public static class Parts
    {
        public static Transform Group(Transform parent, string name, Vector3 position = default)
        {
            var group = new GameObject(name).transform;
            group.SetParent(parent, false);
            group.localPosition = position;
            return group;
        }

        static Transform Shape(PrimitiveType type, Transform parent, string name, Vector3 position, Vector3 scale,
                               Material material)
        {
            var shape = GameObject.CreatePrimitive(type);
            Remove(shape.GetComponent<Collider>()); // (nothing collides: Unity only draws)
            shape.name = name;
            var t = shape.transform;
            t.SetParent(parent, false);
            t.localPosition = position;
            t.localScale = scale;
            shape.GetComponent<Renderer>().sharedMaterial = material;
            return t;
        }

        /// <summary>Destroys an object, in play or (tests) in the editor.</summary>
        public static void Remove(Object thing)
        {
            if (Application.isPlaying) Object.Destroy(thing);
            else Object.DestroyImmediate(thing);
        }

        public static Transform Box(Transform parent, string name, Vector3 position, Vector3 size, Material material) =>
            Shape(PrimitiveType.Cube, parent, name, position, size, material);

        /// <summary>three.js CapsuleGeometry(radius, length): `length` between the caps.</summary>
        public static Transform Capsule(Transform parent, string name, Vector3 position, float radius, float length,
                                        Material material) =>
            Shape(PrimitiveType.Capsule, parent, name, position,
                  new Vector3(2 * radius, (length + 2 * radius) / 2, 2 * radius), material);

        /// <summary>three.js CylinderGeometry(top, bottom, height), as one average radius.</summary>
        public static Transform Cylinder(Transform parent, string name, Vector3 position, float top, float bottom,
                                         float height, Material material) =>
            Shape(PrimitiveType.Cylinder, parent, name, position,
                  new Vector3(top + bottom, height / 2, top + bottom), material);

        public static Transform Sphere(Transform parent, string name, Vector3 position, float radius, Material material) =>
            Shape(PrimitiveType.Sphere, parent, name, position, Vector3.one * (2 * radius), material);

        /// <summary>A lit material in a color: roughness and metalness as three.js has them.</summary>
        public static Material Lit(Color color, float roughness = 0.8f, float metalness = 0)
        {
            var material = new Material(Resources.Load<Material>("Lit")) { color = color };
            material.SetFloat("_Glossiness", 1 - roughness);
            material.SetFloat("_Metallic", metalness);
            return material;
        }

        public static Material Unlit(Color color) =>
            new(Resources.Load<Material>("Line")) { color = color };

        public static Color Hex(string hex, Color fallback = default) =>
            ColorUtility.TryParseHtmlString(hex ?? "", out var c) ? c : fallback;

        /// <summary>Radians to a Unity Euler angle (degrees).</summary>
        public static float Deg(double radians) => (float)(radians * Mathf.Rad2Deg);
    }
}
