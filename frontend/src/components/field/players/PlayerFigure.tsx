"use client";

import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { CanvasTexture, DoubleSide, Group, MeshStandardMaterial, SRGBColorSpace } from "three";
import { toScene } from "../layout";
import type { Kit } from "./kit";
import { hipHeight, type Build, type JointAngles } from "./poses";

/** Where a player is and how he's posed at one instant (field coordinates, radians). */
export interface PlayerFrame {
  x: number;
  y: number;
  facing: number; // 0 faces +x along the field, π/2 faces +y
  angles: JointAngles;
}

export interface PlayerFigureProps {
  build: Build;
  kit: Kit;
  number: number;
  skin: string;
  /** Called every frame with the elapsed time; nothing re-renders. */
  driver: (time: number) => PlayerFrame;
}

/**
 * A low-poly player: helmet and facemask, pads, jersey with numbers, pants, and a jointed
 * skeleton the driver poses every frame.
 */
export function PlayerFigure({ build: b, kit, number, skin, driver }: PlayerFigureProps) {
  const root = useRef<Group>(null);
  const body = useRef<Group>(null);
  const torso = useRef<Group>(null);
  const hipL = useRef<Group>(null);
  const hipR = useRef<Group>(null);
  const kneeL = useRef<Group>(null);
  const kneeR = useRef<Group>(null);
  const shoulderL = useRef<Group>(null);
  const shoulderR = useRef<Group>(null);
  const elbowL = useRef<Group>(null);
  const elbowR = useRef<Group>(null);

  const materials = useMemo(() => ({
    jersey: new MeshStandardMaterial({ color: kit.jersey, roughness: 0.7 }),
    pants: new MeshStandardMaterial({ color: kit.pants, roughness: 0.7 }),
    helmet: new MeshStandardMaterial({ color: kit.helmet, roughness: 0.25, metalness: 0.35 }),
    socks: new MeshStandardMaterial({ color: kit.socks, roughness: 0.8 }),
    skin: new MeshStandardMaterial({ color: skin, roughness: 0.8 }),
    dark: new MeshStandardMaterial({ color: "#111827", roughness: 0.6 }),
    mask: new MeshStandardMaterial({ color: "#d1d5db", roughness: 0.4, metalness: 0.5 }),
  }), [kit, skin]);
  const numberTexture = useNumberTexture(number, kit.numbers);
  useEffect(() => () => Object.values(materials).forEach((m) => m.dispose()), [materials]);

  useFrame((state) => {
    const { x, y, facing, angles: a } = driver(state.clock.elapsedTime);
    const [sx, , sz] = toScene(x, y);
    root.current?.position.set(sx, 0, sz);
    root.current?.rotation.set(0, -facing, 0);
    if (body.current) {
      body.current.position.y = hipHeight(b, a);
      body.current.rotation.z = -a.lie * (Math.PI / 2) * 0.95;
    }
    torso.current?.rotation.set(0, 0, -a.torso);
    hipL.current?.rotation.set(0, 0, a.hipL);
    hipR.current?.rotation.set(0, 0, a.hipR);
    kneeL.current?.rotation.set(0, 0, -a.kneeL);
    kneeR.current?.rotation.set(0, 0, -a.kneeR);
    shoulderL.current?.rotation.set(a.spreadL, 0, a.shoulderL);
    shoulderR.current?.rotation.set(-a.spreadR, 0, a.shoulderR);
    elbowL.current?.rotation.set(0, 0, a.elbowL);
    elbowR.current?.rotation.set(0, 0, a.elbowR);
  });

  const w = b.bulk;
  const hip = 0.11 * w;
  const shoulder = 0.27 * w;
  return (
    <group ref={root}>
      <group ref={body}>
        {/* Pelvis and pants. */}
        <mesh material={materials.pants} position-y={0.02}>
          <boxGeometry args={[0.22 * w, 0.2, 0.36 * w]} />
        </mesh>
        {([["L", hipL, kneeL, -hip], ["R", hipR, kneeR, hip]] as const).map(([side, hipRef, kneeRef, z]) => (
          <group key={side} ref={hipRef} position={[0, 0, z]}>
            <mesh material={materials.pants} position-y={-b.thigh / 2}>
              <capsuleGeometry args={[0.075 * w, b.thigh - 0.1, 3, 8]} />
            </mesh>
            <group ref={kneeRef} position-y={-b.thigh}>
              <mesh material={materials.socks} position-y={-b.shin / 2}>
                <capsuleGeometry args={[0.058 * w, b.shin - 0.08, 3, 8]} />
              </mesh>
              <mesh material={materials.dark} position={[0.05, -b.shin + 0.02, 0]}>
                <boxGeometry args={[0.2, 0.07, 0.1]} />
              </mesh>
            </group>
          </group>
        ))}
        <group ref={torso} position-y={0.08}>
          <mesh material={materials.jersey} position-y={b.torso / 2}>
            <cylinderGeometry args={[0.2 * w, 0.15 * w, b.torso, 10]} />
          </mesh>
          {/* Shoulder pads under the jersey. */}
          <mesh material={materials.jersey} position-y={b.torso * 0.92}>
            <boxGeometry args={[0.32 * w, 0.14, 0.62 * w]} />
          </mesh>
          {/* Numbers on the chest and back. */}
          {numberTexture && [1, -1].map((side) => (
            <mesh key={side} position={[side * 0.205 * w, b.torso * 0.6, 0]}
              rotation-y={side * Math.PI / 2}>
              <planeGeometry args={[0.3 * w, 0.26]} />
              <meshBasicMaterial map={numberTexture} transparent side={DoubleSide} />
            </mesh>
          ))}
          <group position-y={b.torso + b.head * 0.55}>
            <mesh material={materials.helmet}>
              <sphereGeometry args={[b.head * 0.55, 14, 10]} />
            </mesh>
            <mesh material={materials.mask} position={[b.head * 0.45, -b.head * 0.12, 0]}>
              <boxGeometry args={[0.04, b.head * 0.45, b.head * 0.7]} />
            </mesh>
          </group>
          {([["L", shoulderL, elbowL, -shoulder], ["R", shoulderR, elbowR, shoulder]] as const).map(
            ([side, shoulderRef, elbowRef, z]) => (
              <group key={side} ref={shoulderRef} position={[0, b.torso * 0.9, z]}>
                <mesh material={materials.jersey} position-y={-b.upperArm / 2}>
                  <capsuleGeometry args={[0.055 * w, b.upperArm - 0.08, 3, 8]} />
                </mesh>
                <group ref={elbowRef} position-y={-b.upperArm}>
                  <mesh material={materials.skin} position-y={-b.forearm / 2}>
                    <capsuleGeometry args={[0.045 * w, b.forearm - 0.08, 3, 8]} />
                  </mesh>
                  <mesh material={materials.dark} position-y={-b.forearm}>
                    <sphereGeometry args={[0.05, 8, 6]} />
                  </mesh>
                </group>
              </group>
            ))}
        </group>
      </group>
    </group>
  );
}

const numberTextures = new Map<string, CanvasTexture>();

/** A cached canvas texture with a jersey number in the given color. */
function useNumberTexture(number: number, color: string): CanvasTexture | null {
  return useMemo(() => {
    if (typeof document === "undefined") return null;
    const key = `${number}:${color}`;
    const cached = numberTextures.get(key);
    if (cached) return cached;
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 112;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.fillStyle = color;
    ctx.font = "bold 92px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(number), 64, 60);
    const texture = new CanvasTexture(canvas);
    texture.colorSpace = SRGBColorSpace;
    numberTextures.set(key, texture);
    return texture;
  }, [number, color]);
}

/** A football: a prolate spheroid with laces, placed and spun by its driver. */
export function Football({ driver }: { driver: (time: number) => { x: number; y: number; z: number;
                                                                    spin?: number; pitch?: number } }) {
  const ref = useRef<Group>(null);
  useFrame((state) => {
    const { x, y, z, spin = 0, pitch = 0 } = driver(state.clock.elapsedTime);
    const [sx, , sz] = toScene(x, y);
    ref.current?.position.set(sx, z, sz);
    ref.current?.rotation.set(spin, 0, pitch);
  });
  return (
    <group ref={ref}>
      <mesh scale={[0.155, 0.095, 0.095]}>
        <sphereGeometry args={[1, 16, 12]} />
        <meshStandardMaterial color="#7a3e16" roughness={0.6} />
      </mesh>
      <mesh position-y={0.093} scale={[0.06, 0.006, 0.012]}>
        <boxGeometry />
        <meshStandardMaterial color="#f8fafc" />
      </mesh>
    </group>
  );
}
