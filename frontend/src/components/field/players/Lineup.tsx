"use client";

import { useMemo } from "react";
import { WIDTH } from "../layout";
import { defenseSpots, NUMBERS, offenseSpots, spotOnField, TYPICAL, type Package, type Spot } from "./formations";
import { kit, skinTone } from "./kit";
import { Football, PlayerFigure, type PlayerFrame } from "./PlayerFigure";
import { blend, build, pose } from "./poses";

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
