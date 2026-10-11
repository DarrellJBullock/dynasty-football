import { describe, expect, it } from "vitest";
import { canvasSize, drawField, PIXELS_PER_YARD } from "./fieldTexture";

/** Records what drawField paints, with the transform applied to text. */
function recorder() {
  const texts: { value: string; fill: string }[] = [];
  const rects: { fill: string; w: number; h: number }[] = [];
  let fill = "";
  const ctx = {
    set fillStyle(v: string) { fill = v; },
    get fillStyle() { return fill; },
    strokeStyle: "", lineWidth: 0, font: "", textAlign: "", textBaseline: "",
    fillRect: (_x: number, _y: number, w: number, h: number) => rects.push({ fill, w, h }),
    fillText: (value: string) => texts.push({ value, fill }),
    save() {}, restore() {}, translate() {}, rotate() {},
    beginPath() {}, arc() {}, fill() {}, stroke() {},
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, texts, rects };
}

const style = { primary: "#0b2545", secondary: "#c9a227", nickname: "Ironclads", abbreviation: "HFD" };

describe("drawField", () => {
  it("sizes the canvas to the field plus its border", () => {
    const { width, height } = canvasSize();
    expect(width).toBe(124 * PIXELS_PER_YARD);
    expect(height).toBeCloseTo((160 / 3 + 4) * PIXELS_PER_YARD, 0);
  });

  it("paints numbers on both sides, the nickname in both end zones, and the logo", () => {
    const { ctx, texts, rects } = recorder();
    drawField(ctx, style);
    const numbers = texts.filter((t) => /^\d+$/.test(t.value)).map((t) => t.value);
    expect(numbers).toHaveLength(18);
    expect(numbers.filter((n) => n === "50")).toHaveLength(2);
    expect(texts.filter((t) => t.value === "IRONCLADS")).toHaveLength(2);
    expect(texts.some((t) => t.value === "HFD")).toBe(true);
    // Both end zones in the home color, 10 yards deep.
    expect(rects.filter((r) => r.fill === style.primary && r.w === 10 * PIXELS_PER_YARD)).toHaveLength(2);
  });
});
