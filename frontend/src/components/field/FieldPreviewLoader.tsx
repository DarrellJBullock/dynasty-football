"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import type { FieldPreviewProps } from "./FieldPreview";
import { CAMERA_PRESETS, type CameraPreset } from "./layout";

// WebGL only exists in the browser, so the scene is never server-rendered.
const FieldPreview = dynamic(() => import("./FieldPreview"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse rounded-xl bg-turf/10" />,
});

/** The 3D stadium with camera presets to switch between. */
export function FieldPreviewLoader(props: Omit<FieldPreviewProps, "camera">) {
  const [camera, setCamera] = useState<CameraPreset>("overview");
  return (
    <>
      <FieldPreview {...props} camera={camera} />
      <div role="group" aria-label="Camera"
        className="absolute right-3 top-3 flex gap-1 rounded-lg bg-ink-950/70 p-1 backdrop-blur">
        {CAMERA_PRESETS.map(({ key, label }) => (
          <button key={key} type="button" aria-pressed={camera === key}
            className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${
              camera === key ? "bg-gold text-ink-950" : "text-mist hover:text-chalk"}`}
            onClick={() => setCamera(key)}>
            {label}
          </button>
        ))}
      </div>
    </>
  );
}
