"use client";

import dynamic from "next/dynamic";
import type { FieldPreviewProps } from "./FieldPreview";

// WebGL only exists in the browser, so the scene is never server-rendered.
const FieldPreview = dynamic(() => import("./FieldPreview"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse rounded-xl bg-turf/10" />,
});

export function FieldPreviewLoader(props: FieldPreviewProps) {
  return <FieldPreview {...props} />;
}
