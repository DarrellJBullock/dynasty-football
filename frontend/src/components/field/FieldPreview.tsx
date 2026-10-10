"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import type { Group } from "three";

// 1 world unit = 1 yard. Field is 120 x 53.3 including end zones.
const LENGTH = 120;
const WIDTH = 53.3;

export interface FieldPreviewProps {
  homeColor: string;
  homeAccent: string;
  awayColor: string;
}

/**
 * Decorative stadium preview for the dashboard. This is intentionally a static
 * scene — the game engine (players, physics, cameras) arrives in Milestone 4.
 */
export default function FieldPreview(props: FieldPreviewProps) {
  return (
    <Canvas
      camera={{ position: [0, 58, 78], fov: 42 }}
      onCreated={({ camera }) => camera.lookAt(0, 0, 0)}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      aria-label="3D field preview"
    >
      <ambientLight intensity={0.55} />
      <directionalLight position={[30, 60, 20]} intensity={1.6} />
      <hemisphereLight args={["#bcd8ff", "#0b2a18", 0.35]} />
      <Stadium {...props} />
    </Canvas>
  );
}

function Stadium({ homeColor, homeAccent, awayColor }: FieldPreviewProps) {
  const group = useRef<Group>(null);
  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += delta * 0.08;
  });

  const yardLines = useMemo(() => {
    const lines: number[] = [];
    for (let yard = 0; yard <= 100; yard += 5) lines.push(yard - 50);
    return lines;
  }, []);

  return (
    <group ref={group} rotation={[0, -0.5, 0]}>
      {/* turf apron */}
      <mesh rotation-x={-Math.PI / 2} position-y={-0.05}>
        <planeGeometry args={[LENGTH + 14, WIDTH + 14]} />
        <meshStandardMaterial color="#0f3d25" roughness={1} />
      </mesh>
      {/* playing field with mowing stripes */}
      {Array.from({ length: 20 }, (_, i) => (
        <mesh key={i} rotation-x={-Math.PI / 2} position={[-47.5 + i * 5, 0, 0]}>
          <planeGeometry args={[5, WIDTH]} />
          <meshStandardMaterial color={i % 2 ? "#1d7146" : "#1a6840"} roughness={0.95} />
        </mesh>
      ))}
      {/* end zones */}
      {[-55, 55].map((x, i) => (
        <mesh key={x} rotation-x={-Math.PI / 2} position={[x, 0.01, 0]}>
          <planeGeometry args={[10, WIDTH]} />
          <meshStandardMaterial color={i === 0 ? homeColor : awayColor} roughness={0.8} />
        </mesh>
      ))}
      {/* yard lines */}
      {yardLines.map((x) => (
        <mesh key={x} rotation-x={-Math.PI / 2} position={[x, 0.02, 0]}>
          <planeGeometry args={[x % 10 === 0 ? 0.35 : 0.2, WIDTH]} />
          <meshBasicMaterial color="#f4f7f5" transparent opacity={x === 0 ? 1 : 0.85} />
        </mesh>
      ))}
      {/* midfield logo */}
      <mesh rotation-x={-Math.PI / 2} position-y={0.03}>
        <circleGeometry args={[4.5, 48]} />
        <meshStandardMaterial color={homeColor} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0.035}>
        <ringGeometry args={[4.5, 5.1, 48]} />
        <meshStandardMaterial color={homeAccent} />
      </mesh>
      {/* goal posts */}
      {[-60, 60].map((x) => (
        <GoalPost key={x} x={x} />
      ))}
      <Formation x={-2} color={homeColor} accent={homeAccent} facing={1} />
      <Formation x={2} color={awayColor} accent="#e8edf3" facing={-1} />
    </group>
  );
}

function GoalPost({ x }: { x: number }) {
  const color = "#f2c94c";
  return (
    <group position={[x, 0, 0]}>
      <mesh position-y={2.5}>
        <cylinderGeometry args={[0.2, 0.2, 5]} />
        <meshStandardMaterial color={color} metalness={0.3} roughness={0.4} />
      </mesh>
      <mesh position-y={5} rotation-x={Math.PI / 2}>
        <cylinderGeometry args={[0.15, 0.15, 6.2]} />
        <meshStandardMaterial color={color} metalness={0.3} roughness={0.4} />
      </mesh>
      {[-3.1, 3.1].map((z) => (
        <mesh key={z} position={[0, 9, z]}>
          <cylinderGeometry args={[0.12, 0.12, 8]} />
          <meshStandardMaterial color={color} metalness={0.3} roughness={0.4} />
        </mesh>
      ))}
    </group>
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
