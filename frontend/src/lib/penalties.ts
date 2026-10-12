/** Penalties as the broadcast and the 3D replay name them. */

/** Foul names, as the engine's play-by-play has them (`app/sim/penalties.py` NAMES). */
export const PENALTY_NAMES: Record<string, string> = {
  false_start: "False start",
  delay_of_game: "Delay of game",
  offside: "Offside",
  neutral_zone_infraction: "Neutral zone infraction",
  holding: "Offensive holding",
  illegal_formation: "Illegal formation",
  offensive_pass_interference: "Offensive pass interference",
  intentional_grounding: "Intentional grounding",
  defensive_holding: "Defensive holding",
  illegal_contact: "Illegal contact",
  pass_interference: "Defensive pass interference",
  roughing_the_passer: "Roughing the passer",
  unnecessary_roughness: "Unnecessary roughness",
  face_mask: "Face mask",
};

export function penaltyName(kind: string): string {
  return PENALTY_NAMES[kind] ?? kind.replaceAll("_", " ");
}
