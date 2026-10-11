"use client";

import { useMemo } from "react";
import { WIDTH } from "../layout";
import { defenseSpots, offenseSpots, spotOnField, type Package, type Spot } from "./formations";
import { kit, skinTone } from "./kit";
import { Football, PlayerFigure, type PlayerFrame } from "./PlayerFigure";
import { blend, build, pose } from "./poses";

/** Typical size by position (inches, pounds) and a typical number by role, for lineups
 * that aren't real rosters (the dashboard's stadium). */
const TYPICAL: Record<string, [number, number]> = {
  QB: [75, 225], RB: [70, 215], WR: [73, 200], TE: [77, 250], OT: [78, 315], OG: [76, 315],
  C: [75, 305], DE: [76, 270], DT: [75, 310], OLB: [75, 245], MLB: [74, 240], CB: [71, 195],
  FS: [72, 205], SS: [72, 210],
};
const NUMBERS: Record<string, number> = {
  QB: 12, RB: 28, X: 11, Z: 84, SLOT: 17, TE: 87, LT: 74, RT: 71, LG: 66, RG: 63, C: 55,
  LDE: 91, RDE: 97, LDT: 93, RDT: 99, SAM: 52, WILL: 54, MIKE: 50, CB1: 24, CB2: 21, NB: 31,
  DB: 37, FS: 29, SS: 33,
};

interface TeamColors { primary_color: string; secondary_color: string }

/** Both teams lined up at the line of scrimmage, in stance, breathing. */
export function Lineup({ offense, defense, los, direction = 1, pkg = "base", ballY = WIDTH / 2 }: {
  offense: TeamColors;
  defense: TeamColors;
  los: number;
  direction?: 1 | -1;
  pkg?: Package;
  ballY?: number;
}) {
  const players = useMemo(() => [
    ...offenseSpots().map((spot, i) => ({ spot, side: "offense" as const, team: offense, home: true, id: i + 1 })),
    ...defenseSpots(pkg).map((spot, i) => ({ spot, side: "defense" as const, team: defense, home: false, id: i + 20 })),
  ], [offense, defense, pkg]);

  return (
    <group>
      {players.map(({ spot, side, team, home, id }) => (
        <StandingPlayer key={`${side}-${spot.role}`} spot={spot} side={side} los={los} ballY={ballY}
          direction={direction} kitColors={kit(team, home)} id={id} />
      ))}
      <Football driver={() => ({ x: los, y: ballY, z: 0.1, pitch: 0 })} />
    </group>
  );
}

function StandingPlayer({ spot, side, los, ballY, direction, kitColors, id }: {
  spot: Spot; side: "offense" | "defense"; los: number; ballY: number; direction: 1 | -1;
  kitColors: ReturnType<typeof kit>; id: number;
}) {
  const [height, weight] = TYPICAL[spot.position];
  const figure = useMemo(() => build(height, weight), [height, weight]);
  const place = spotOnField(spot, side, los, ballY, direction);
  const stance = pose(spot.stance);
  const set = pose(spot.stance === "stance3" ? "stance3" : "stand");
  // A slow, slightly different breath for everyone.
  const driver = (time: number): PlayerFrame => ({
    ...place,
    angles: blend(stance, set, 0.06 + 0.06 * Math.sin(time * 1.3 + id)),
  });
  return <PlayerFigure build={figure} kit={kitColors} number={NUMBERS[spot.role] ?? id}
    skin={skinTone(id * 7919)} driver={driver} />;
}
