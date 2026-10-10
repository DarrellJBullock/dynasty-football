// Display grouping for the 24 player attributes (see backend/app/domain/ratings.py).
export const ATTRIBUTE_CATEGORIES: { label: string; attributes: string[] }[] = [
  {
    label: "Physical",
    attributes: ["speed", "acceleration", "strength", "agility", "stamina", "toughness"],
  },
  { label: "Mental", attributes: ["awareness", "play_recognition"] },
  { label: "Passing", attributes: ["throw_power", "throw_accuracy"] },
  { label: "Ball Carrier", attributes: ["carrying", "ball_carrier_vision", "elusiveness"] },
  { label: "Receiving", attributes: ["catching", "route_running"] },
  { label: "Blocking", attributes: ["run_blocking", "pass_blocking"] },
  {
    label: "Defense",
    attributes: ["tackling", "pass_rush", "block_shedding", "man_coverage", "zone_coverage"],
  },
  { label: "Kicking", attributes: ["kick_power", "kick_accuracy"] },
];

/** Short labels for compact rating chips in tables. */
export const ATTRIBUTE_ABBREVIATIONS: Record<string, string> = {
  speed: "SPD", acceleration: "ACC", strength: "STR", agility: "AGI", stamina: "STA",
  toughness: "TGH", awareness: "AWR", throw_power: "THP", throw_accuracy: "THA",
  carrying: "CAR", ball_carrier_vision: "BCV", elusiveness: "ELU", catching: "CTH",
  route_running: "RTE", run_blocking: "RBK", pass_blocking: "PBK", tackling: "TAK",
  pass_rush: "PRS", block_shedding: "BSH", man_coverage: "MCV", zone_coverage: "ZCV",
  play_recognition: "PRC", kick_power: "KPW", kick_accuracy: "KAC",
};
