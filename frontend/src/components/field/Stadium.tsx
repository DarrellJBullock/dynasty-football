"use client";

import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { CanvasTexture, Color, InstancedMesh, Matrix4, SRGBColorSpace } from "three";
import { canvasSize, drawField, type FieldStyle } from "./fieldTexture";
import { BORDER, GOALPOST, LENGTH, WIDTH, toScene } from "./layout";

export interface StadiumProps {
  field: FieldStyle;
  /** Lines to draw (field x): line of scrimmage, first down. */
  lineOfScrimmage?: number | null;
  firstDownLine?: number | null;
}

/** The full stadium: field, goal posts, stands and crowd, light towers, lighting. */
export function Stadium({ field, lineOfScrimmage, firstDownLine }: StadiumProps) {
  return (
    <group>
      <Lighting />
      <FieldSurface field={field} />
      <GoalPost x={0} />
      <GoalPost x={LENGTH} />
      <Stands crowdColors={[field.primary, field.secondary]} />
      <LightTowers />
      {lineOfScrimmage != null && <FieldLine x={lineOfScrimmage} color="#3b82f6" />}
      {firstDownLine != null && <FieldLine x={firstDownLine} color="#facc15" />}
    </group>
  );
}

function Lighting() {
  return (
    <>
      <hemisphereLight args={["#cfe3ff", "#14321f", 0.55]} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[40, 80, 30]} intensity={1.5} />
      <directionalLight position={[-50, 60, -40]} intensity={0.6} />
    </>
  );
}

function FieldSurface({ field }: { field: FieldStyle }) {
  const texture = useMemo(() => {
    if (typeof document === "undefined") return null;
    const canvas = document.createElement("canvas");
    const { width, height } = canvasSize();
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    drawField(ctx, field);
    const result = new CanvasTexture(canvas);
    result.colorSpace = SRGBColorSpace;
    result.anisotropy = 8;
    return result;
  }, [field]);
  useEffect(() => () => texture?.dispose(), [texture]);

  return (
    <group>
      {/* Ground beyond the field (out to the stands). */}
      <mesh rotation-x={-Math.PI / 2} position-y={-0.05}>
        <planeGeometry args={[LENGTH + 60, WIDTH + 60]} />
        <meshStandardMaterial color="#2a2f36" roughness={1} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} receiveShadow>
        <planeGeometry args={[LENGTH + 2 * BORDER, WIDTH + 2 * BORDER]} />
        {texture ? <meshStandardMaterial map={texture} roughness={0.95} />
          : <meshStandardMaterial color="#1d6b40" roughness={0.95} />}
      </mesh>
    </group>
  );
}

function FieldLine({ x, color }: { x: number; color: string }) {
  const [sx] = toScene(x, 0);
  return (
    <mesh rotation-x={-Math.PI / 2} position={[sx, 0.02, 0]}>
      <planeGeometry args={[0.3, WIDTH]} />
      <meshBasicMaterial color={color} transparent opacity={0.9} depthWrite={false} />
    </mesh>
  );
}

const POST = "#f2c94c";

/** A pro goal post on the end line: a curved-neck base, 10-ft crossbar, uprights 18'6"
 * apart rising 35 ft above it. */
function GoalPost({ x }: { x: number }) {
  const [sx] = toScene(x, WIDTH / 2);
  const out = x === 0 ? -1 : 1; // the base stands behind the end line
  const { crossbar, width, upright } = GOALPOST;
  return (
    <group position={[sx, 0, 0]}>
      <mesh position={[out * 1.6, crossbar / 2, 0]}>
        <cylinderGeometry args={[0.18, 0.22, crossbar]} />
        <meshStandardMaterial color={POST} metalness={0.3} roughness={0.4} />
      </mesh>
      <mesh position={[out * 0.8, crossbar, 0]} rotation-z={Math.PI / 2}>
        <cylinderGeometry args={[0.13, 0.13, 1.6]} />
        <meshStandardMaterial color={POST} metalness={0.3} roughness={0.4} />
      </mesh>
      <mesh position={[0, crossbar, 0]} rotation-x={Math.PI / 2}>
        <cylinderGeometry args={[0.12, 0.12, width]} />
        <meshStandardMaterial color={POST} metalness={0.3} roughness={0.4} />
      </mesh>
      {[-width / 2, width / 2].map((z) => (
        <mesh key={z} position={[0, crossbar + upright / 2, z]}>
          <cylinderGeometry args={[0.09, 0.09, upright]} />
          <meshStandardMaterial color={POST} metalness={0.3} roughness={0.4} />
        </mesh>
      ))}
    </group>
  );
}

// ---------- stands ----------

const STAND_GAP = 9; // yards between the field's border and the first row
const ROWS = 14;
const ROW_DEPTH = 1.6;
const ROW_RISE = 1.1;
const SEAT_SPACING = 1.1;

interface Section { cx: number; cz: number; along: number; facing: number; rotated: boolean }

/** The four banks of stands around the field, each facing in. */
function sections(): Section[] {
  const halfL = LENGTH / 2 + BORDER + STAND_GAP;
  const halfW = WIDTH / 2 + BORDER + STAND_GAP;
  return [
    { cx: 0, cz: halfW, along: LENGTH + 10, facing: 1, rotated: false },
    { cx: 0, cz: -halfW, along: LENGTH + 10, facing: -1, rotated: false },
    { cx: halfL, cz: 0, along: WIDTH + 10, facing: 1, rotated: true },
    { cx: -halfL, cz: 0, along: WIDTH + 10, facing: -1, rotated: true },
  ];
}

/** A small deterministic generator, so the crowd looks the same every time. */
function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

function Stands({ crowdColors }: { crowdColors: string[] }) {
  const crowd = useRef<InstancedMesh>(null);
  const seats = useMemo(() => {
    const out: [number, number, number][] = [];
    for (const s of sections()) {
      const count = Math.floor(s.along / SEAT_SPACING);
      for (let row = 0; row < ROWS; row++) {
        const depth = row * ROW_DEPTH + ROW_DEPTH / 2;
        const height = row * ROW_RISE + ROW_RISE + 0.45;
        for (let i = 0; i < count; i++) {
          const along = -s.along / 2 + (i + 0.5) * SEAT_SPACING;
          out.push(s.rotated
            ? [s.cx + s.facing * depth, height, along]
            : [along, height, s.cz + s.facing * depth]);
        }
      }
    }
    return out;
  }, []);

  useLayoutEffect(() => {
    const mesh = crowd.current;
    if (!mesh) return;
    const random = seeded(7);
    const palette = [...crowdColors, "#e5e7eb", "#4b5563", "#1f2937", "#9ca3af"].map((c) => new Color(c));
    const matrix = new Matrix4();
    seats.forEach(([x, y, z], i) => {
      matrix.makeTranslation(x, y + random() * 0.15, z);
      mesh.setMatrixAt(i, matrix);
      // About half the fans wear the home team's colors.
      const pick = random() < 0.5 ? Math.floor(random() * crowdColors.length)
        : crowdColors.length + Math.floor(random() * 4);
      mesh.setColorAt(i, palette[pick]);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [seats, crowdColors]);

  return (
    <group>
      {sections().map((s, i) => (
        <group key={i}>
          {Array.from({ length: ROWS }, (_, row) => {
            const depth = row * ROW_DEPTH + ROW_DEPTH / 2;
            const height = (row + 1) * ROW_RISE;
            const position: [number, number, number] = s.rotated
              ? [s.cx + s.facing * depth, height / 2, 0]
              : [0, height / 2, s.cz + s.facing * depth];
            const size: [number, number, number] = s.rotated
              ? [ROW_DEPTH, height, s.along] : [s.along, height, ROW_DEPTH];
            return (
              <mesh key={row} position={position}>
                <boxGeometry args={size} />
                <meshStandardMaterial color={row % 2 ? "#3a414b" : "#343a43"} roughness={0.9} />
              </mesh>
            );
          })}
        </group>
      ))}
      <instancedMesh ref={crowd} args={[undefined, undefined, seats.length]}>
        <boxGeometry args={[0.7, 0.9, 0.5]} />
        <meshStandardMaterial roughness={0.8} />
      </instancedMesh>
    </group>
  );
}

function LightTowers() {
  const x = LENGTH / 2 + BORDER + STAND_GAP + ROWS * ROW_DEPTH * 0.8;
  const z = WIDTH / 2 + BORDER + STAND_GAP + ROWS * ROW_DEPTH * 0.8;
  const towers: [number, number][] = [[x, z], [-x, z], [x, -z], [-x, -z]];
  return (
    <group>
      {towers.map(([tx, tz]) => (
        <group key={`${tx}-${tz}`} position={[tx, 0, tz]}>
          <mesh position-y={24}>
            <cylinderGeometry args={[0.5, 0.8, 48]} />
            <meshStandardMaterial color="#6b7280" metalness={0.4} roughness={0.5} />
          </mesh>
          {/* The bank of lamps, angled toward midfield. */}
          <mesh position-y={49} rotation-y={Math.atan2(tx, tz)} rotation-x={-0.35}>
            <boxGeometry args={[9, 4, 0.8]} />
            <meshStandardMaterial color="#f8fafc" emissive="#fff7d6" emissiveIntensity={1.4} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

