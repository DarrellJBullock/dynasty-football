/** Uniforms and skin tones for the player figures. Pure. */

export interface Kit {
  jersey: string;
  numbers: string;
  pants: string;
  helmet: string;
  socks: string;
}

export const AWAY_JERSEY = "#f3f4f6";

/** Relative luminance of a #rrggbb color (WCAG). */
export function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** The most readable of the candidates on `background`. */
function readable(background: string, candidates: string[]): string {
  return candidates.reduce((best, c) => (contrast(background, c) > contrast(background, best) ? c : best));
}

/** Home teams wear their primary color; away teams wear white. */
export function kit(team: { primary_color: string; secondary_color: string }, home: boolean): Kit {
  const { primary_color: primary, secondary_color: secondary } = team;
  const jersey = home ? primary : AWAY_JERSEY;
  return {
    jersey,
    numbers: readable(jersey, home ? [secondary, "#ffffff", "#111827"] : [primary, secondary, "#111827"]),
    pants: home ? secondary : primary,
    helmet: primary,
    socks: home ? primary : AWAY_JERSEY,
  };
}

const SKIN = ["#f1c9a5", "#e0ac83", "#c68b59", "#a8693f", "#8d5524", "#6b3e1f", "#4a2a17"];

/** A stable skin tone per player. */
export function skinTone(playerId: number): string {
  return SKIN[Math.abs(Math.imul(playerId, 2654435761)) % SKIN.length];
}
