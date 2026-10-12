"use client";

import { Canvas } from "@react-three/fiber";
import { CameraRig } from "./CameraRig";
import { cameraShot, type CameraPreset } from "./layout";
import { Lineup } from "./players/Lineup";
import { Stadium } from "./Stadium";

export interface FieldPreviewProps {
  homeColor: string;
  homeAccent: string;
  awayColor: string;
  awayAccent?: string;
  nickname: string;
  abbreviation: string;
  camera?: CameraPreset;
}

/**
 * The dashboard's stadium: the home team lined up at midfield against its next opponent.
 */
export default function FieldPreview({ homeColor, homeAccent, awayColor, awayAccent = "#e5e7eb",
                                       nickname, abbreviation, camera = "overview" }: FieldPreviewProps) {
  const start = cameraShot("overview");
  return (
    <Canvas
      camera={{ position: start.position, fov: start.fov, far: 600 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      role="img"
      aria-label="3D field preview"
    >
      <CameraRig preset={camera} />
      <Stadium field={{ primary: homeColor, secondary: homeAccent, nickname, abbreviation }}
        lineOfScrimmage={60} firstDownLine={70} />
      <Lineup offense={{ primary_color: homeColor, secondary_color: homeAccent }}
        defense={{ primary_color: awayColor, secondary_color: awayAccent }} los={60} />
    </Canvas>
  );
}
