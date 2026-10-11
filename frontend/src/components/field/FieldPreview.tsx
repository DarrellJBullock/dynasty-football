"use client";

import { Canvas } from "@react-three/fiber";
import { CameraRig } from "./CameraRig";
import { cameraShot, type CameraPreset } from "./layout";
import { Stadium } from "./Stadium";

export interface FieldPreviewProps {
  homeColor: string;
  homeAccent: string;
  awayColor: string;
  nickname: string;
  abbreviation: string;
  camera?: CameraPreset;
}

/**
 * The dashboard's stadium: the full Milestone 4 scene with a lineup at midfield (players
 * arrive with the playback viewer).
 */
export default function FieldPreview({ homeColor, homeAccent, awayColor, nickname, abbreviation,
                                       camera = "overview" }: FieldPreviewProps) {
  const start = cameraShot("overview");
  return (
    <Canvas
      camera={{ position: start.position, fov: start.fov, far: 600 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      aria-label="3D field preview"
    >
      <CameraRig preset={camera} />
      <Stadium field={{ primary: homeColor, secondary: homeAccent, nickname, abbreviation }}
        lineOfScrimmage={60} firstDownLine={70} />
      <Formation x={-2} color={homeColor} accent={homeAccent} facing={1} />
      <Formation x={2} color={awayColor} accent="#e8edf3" facing={-1} />
    </Canvas>
  );
}

// Rough 11-man alignment (offset from the line of scrimmage, lateral), in yards.
const ALIGNMENT: [number, number][] = [
  [1, 0], [1, -1.5], [1, 1.5], [1, -3], [1, 3], // line
  [1.5, -14], [1.5, 15], [2, 7], // receivers
  [4, 0], [7, 0], // QB + RB
  [1, 5], // TE
];

function Formation({
  x,
  color,
  accent,
  facing,
}: {
  x: number;
  color: string;
  accent: string;
  facing: 1 | -1;
}) {
  return (
    <group position-x={x}>
      {ALIGNMENT.map(([depth, lateral], i) => (
        <group key={i} position={[-facing * depth, 0, lateral]}>
          <mesh position-y={0.9}>
            <capsuleGeometry args={[0.45, 0.9, 4, 12]} />
            <meshStandardMaterial color={color} roughness={0.5} />
          </mesh>
          <mesh position-y={2.05}>
            <sphereGeometry args={[0.36, 16, 12]} />
            <meshStandardMaterial color={accent} metalness={0.4} roughness={0.3} />
          </mesh>
        </group>
      ))}
    </group>
  );
}
