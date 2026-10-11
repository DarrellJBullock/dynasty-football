import {
  BORDER,
  END_ZONE,
  HASH_LENGTH,
  LENGTH,
  NUMBER_HEIGHT,
  NUMBER_INSET,
  WIDTH,
  hashRows,
  yardLines,
  yardNumbers,
} from "./layout";

export interface FieldStyle {
  primary: string; // home team colors: end zones and the midfield logo
  secondary: string;
  nickname: string; // painted in both end zones
  abbreviation: string; // at midfield
}

export const PIXELS_PER_YARD = 24;
const TURF = ["#1d6b40", "#1a6239"];
const PAINT = "#f4f6f2";

/** The canvas size for the whole surface, border included. */
export function canvasSize(ppy = PIXELS_PER_YARD): { width: number; height: number } {
  return { width: Math.round((LENGTH + 2 * BORDER) * ppy), height: Math.round((WIDTH + 2 * BORDER) * ppy) };
}

/**
 * Paint the field onto a 2D canvas: canvas x follows field x and canvas y follows field y
 * (the top edge is the y = 0 sideline), offset by the border.
 */
export function drawField(ctx: CanvasRenderingContext2D, style: FieldStyle, ppy = PIXELS_PER_YARD): void {
  const px = (yards: number) => yards * ppy;
  const fx = (x: number) => px(x + BORDER);
  const fy = (y: number) => px(y + BORDER);
  const { width, height } = canvasSize(ppy);

  ctx.fillStyle = "#17552f"; // the border/team area
  ctx.fillRect(0, 0, width, height);

  // Mowing stripes, 5 yards wide, goal line to goal line; team-colored end zones.
  for (let i = 0; i < 20; i++) {
    ctx.fillStyle = TURF[i % 2];
    ctx.fillRect(fx(END_ZONE + i * 5), fy(0), px(5), px(WIDTH));
  }
  ctx.fillStyle = style.primary;
  ctx.fillRect(fx(0), fy(0), px(END_ZONE), px(WIDTH));
  ctx.fillRect(fx(LENGTH - END_ZONE), fy(0), px(END_ZONE), px(WIDTH));

  ctx.fillStyle = PAINT;
  // Sidelines and end lines (6 ft wide, outside the field of play).
  ctx.fillRect(fx(-2), fy(-2), px(LENGTH + 4), px(2));
  ctx.fillRect(fx(-2), fy(WIDTH), px(LENGTH + 4), px(2));
  ctx.fillRect(fx(-2), fy(0), px(2), px(WIDTH));
  ctx.fillRect(fx(LENGTH), fy(0), px(2), px(WIDTH));
  // Yard lines (goal lines twice as wide).
  for (const x of yardLines()) {
    const w = x === END_ZONE || x === LENGTH - END_ZONE ? 0.22 : 0.11;
    ctx.fillRect(fx(x) - px(w) / 2, fy(0), px(w), px(WIDTH));
  }
  // Hash marks and sideline marks, every yard.
  for (let x = END_ZONE + 1; x < LENGTH - END_ZONE; x++) {
    if ((x - END_ZONE) % 5 === 0) continue;
    for (const y of hashRows()) {
      ctx.fillRect(fx(x) - px(0.06), fy(y) - px(HASH_LENGTH) / 2, px(0.12), px(HASH_LENGTH));
    }
  }
  // Two-point conversion marks, 2 yards out.
  for (const x of [END_ZONE + 2, LENGTH - END_ZONE - 2]) {
    ctx.fillRect(fx(x) - px(0.06), fy(WIDTH / 2) - px(0.5), px(0.12), px(1));
  }

  // Yard numbers: upright from the near sideline, upside down from the far one.
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `bold ${px(NUMBER_HEIGHT)}px sans-serif`;
  for (const { x, label } of yardNumbers()) {
    text(ctx, label, fx(x), fy(WIDTH - NUMBER_INSET + NUMBER_HEIGHT / 2), 0);
    text(ctx, label, fx(x), fy(NUMBER_INSET - NUMBER_HEIGHT / 2), Math.PI);
  }

  // End zones: the nickname, reading out from each goal line.
  ctx.font = `900 ${px(5)}px sans-serif`;
  ctx.fillStyle = style.secondary;
  const name = style.nickname.toUpperCase();
  text(ctx, name, fx(END_ZONE / 2), fy(WIDTH / 2), -Math.PI / 2);
  text(ctx, name, fx(LENGTH - END_ZONE / 2), fy(WIDTH / 2), Math.PI / 2);

  // Midfield logo.
  ctx.beginPath();
  ctx.arc(fx(LENGTH / 2), fy(WIDTH / 2), px(4.6), 0, Math.PI * 2);
  ctx.fillStyle = style.primary;
  ctx.fill();
  ctx.lineWidth = px(0.5);
  ctx.strokeStyle = style.secondary;
  ctx.stroke();
  ctx.fillStyle = PAINT;
  ctx.font = `900 ${px(2.6)}px sans-serif`;
  text(ctx, style.abbreviation, fx(LENGTH / 2), fy(WIDTH / 2), 0);
}

function text(ctx: CanvasRenderingContext2D, value: string, x: number, y: number, angle: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillText(value, 0, 0);
  ctx.restore();
}
