/**
 * The sound engine (docs/design/sound.md §3): every sound synthesized with the Web Audio
 * API (noise, filters and envelopes; oscillators for whistles), so there are no audio
 * files. One engine for the page; the viewers play cues on it as their playhead passes
 * them (lib/sound/useGameSound.ts).
 */

import type { SoundCue, SoundName } from "./cues";

type Ctx = AudioContext;

export interface SoundMix { volume: number; effects: boolean; crowd: boolean }

/** What a test (Playwright) can see: the context's state and the last sounds played. */
export interface SoundProbe { state: string; played: SoundName[] }

declare global {
  interface Window { dynastySound?: SoundProbe }
}

export class SoundEngine {
  private readonly master: GainNode;
  private readonly effects: GainNode;
  private readonly crowd: GainNode; // the crowd's bed and reactions
  private readonly bed: GainNode; // the bed's level (the situation's)
  private readonly noise: AudioBuffer;
  private readonly probe: SoundProbe;

  constructor(private readonly ctx: Ctx) {
    this.master = this.gain(1, ctx.destination);
    this.effects = this.gain(1, this.master);
    this.crowd = this.gain(1, this.master);
    this.bed = this.gain(0, this.crowd);
    this.noise = this.whiteNoise(2);
    this.probe = { state: ctx.state, played: [] };
    window.dynastySound = this.probe;
    ctx.onstatechange = () => { this.probe.state = ctx.state; };
    this.startBed();
  }

  /** The engine, or null where there's no Web Audio. */
  static create(): SoundEngine | null {
    const Audio = typeof window !== "undefined" ? window.AudioContext : undefined;
    return Audio ? new SoundEngine(new Audio()) : null;
  }

  get state(): string { return this.ctx.state; }

  /** (Browsers start audio only after the visitor interacts with the page.) */
  resume(): Promise<void> { return this.ctx.resume(); }
  suspend(): Promise<void> { return this.ctx.suspend(); }

  setMix({ volume, effects, crowd }: SoundMix) {
    const now = this.ctx.currentTime;
    this.master.gain.setTargetAtTime(Math.max(0, Math.min(1, volume)), now, 0.05);
    this.effects.gain.setTargetAtTime(effects ? 1 : 0, now, 0.05);
    this.crowd.gain.setTargetAtTime(crowd ? 1 : 0, now, 0.05);
  }

  /** The crowd's level for the situation (0–1), eased in over a second or two. */
  setCrowdLevel(level: number) {
    this.bed.gain.setTargetAtTime(level * 0.5, this.ctx.currentTime, 0.8);
  }

  /** Plays a cue now (`scale` turns it down, e.g. during a replay). */
  play(cue: SoundCue, scale = 1) {
    const g = cue.gain * scale;
    this.probe.played = [...this.probe.played.slice(-49), cue.sound];
    switch (cue.sound) {
      case "cadence": return this.cadence(g);
      case "snap": return this.thud(g * 0.7, 140, 0.1);
      case "catch": return this.burst(g * 0.5, "bandpass", 1600, 0.05, this.effects);
      case "kick": this.thud(g, 110, 0.14); return this.burst(g * 0.6, "highpass", 2200, 0.03, this.effects);
      case "hit": this.thud(g * 0.8, 90, 0.12); return this.burst(g * 0.6, "lowpass", 900, 0.12, this.effects);
      case "bigHit": this.thud(g, 75, 0.2); return this.burst(g * 0.9, "lowpass", 1100, 0.2, this.effects);
      case "whistle": return this.whistle(g, 0.55, 0);
      case "flag": this.whistle(g, 0.18, 0); return this.whistle(g, 0.18, 0.25);
      case "swell": return this.swell(g, cue.duration ?? 1.5);
      case "cheer": return this.roar(g, 1250, 1250, 2.4);
      case "groan": return this.roar(g * 0.8, 480, 260, 1.8);
    }
  }

  close(): Promise<void> {
    if (window.dynastySound === this.probe) delete window.dynastySound;
    return this.ctx.close();
  }

  // ---------- building blocks ----------

  private gain(value: number, to: AudioNode): GainNode {
    const node = this.ctx.createGain();
    node.gain.value = value;
    node.connect(to);
    return node;
  }

  private whiteNoise(seconds: number): AudioBuffer {
    const buffer = this.ctx.createBuffer(1, Math.floor(this.ctx.sampleRate * seconds), this.ctx.sampleRate);
    const data = buffer.getChannelData(0);
    let seed = 7; // (deterministic noise: the same sound every time)
    for (let i = 0; i < data.length; i++) {
      seed = (seed * 1664525 + 1013904223) % 4294967296;
      data[i] = (seed / 4294967296) * 2 - 1;
    }
    return buffer;
  }

  private source(loop = false): AudioBufferSourceNode {
    const node = this.ctx.createBufferSource();
    node.buffer = this.noise;
    node.loop = loop;
    return node;
  }

  /** The crowd's bed: low murmur, always on, at the situation's level. */
  private startBed() {
    const noise = this.source(true);
    const band = this.ctx.createBiquadFilter();
    band.type = "bandpass";
    band.frequency.value = 650;
    band.Q.value = 0.6;
    const murmur = this.ctx.createGain();
    murmur.gain.value = 0.8;
    const lfo = this.ctx.createOscillator(); // the crowd's ebb and flow
    lfo.frequency.value = 0.35;
    const depth = this.ctx.createGain();
    depth.gain.value = 0.15;
    lfo.connect(depth).connect(murmur.gain);
    noise.connect(band).connect(murmur).connect(this.bed);
    noise.start();
    lfo.start();
  }

  /** A short filtered noise burst (pads, clicks, the ball). */
  private burst(gain: number, type: BiquadFilterType, frequency: number, length: number, to: AudioNode) {
    const now = this.ctx.currentTime;
    const noise = this.source();
    const filter = this.ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = frequency;
    const env = this.ctx.createGain();
    env.gain.setValueAtTime(gain, now);
    env.gain.exponentialRampToValueAtTime(0.001, now + length);
    noise.connect(filter).connect(env).connect(to);
    noise.start(now, Math.random() * 1.5, length + 0.05);
  }

  /** A low thump that drops in pitch (a body, a boot on the ball). */
  private thud(gain: number, frequency: number, length: number) {
    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    osc.frequency.setValueAtTime(frequency, now);
    osc.frequency.exponentialRampToValueAtTime(frequency * 0.45, now + length);
    const env = this.ctx.createGain();
    env.gain.setValueAtTime(gain, now);
    env.gain.exponentialRampToValueAtTime(0.001, now + length);
    osc.connect(env).connect(this.effects);
    osc.start(now);
    osc.stop(now + length + 0.05);
  }

  /** The quarterback's "Set… hut!": two short voiced barks. */
  private cadence(gain: number) {
    const now = this.ctx.currentTime;
    for (const [at, pitch] of [[0, 190], [0.32, 210]] as const) {
      const osc = this.ctx.createOscillator();
      osc.type = "sawtooth";
      osc.frequency.value = pitch;
      const formant = this.ctx.createBiquadFilter(); // an "uh" vowel
      formant.type = "bandpass";
      formant.frequency.value = 750;
      formant.Q.value = 4;
      const env = this.ctx.createGain();
      env.gain.setValueAtTime(0, now + at);
      env.gain.linearRampToValueAtTime(gain * 0.5, now + at + 0.02);
      env.gain.exponentialRampToValueAtTime(0.001, now + at + 0.16);
      osc.connect(formant).connect(env).connect(this.effects);
      osc.start(now + at);
      osc.stop(now + at + 0.2);
    }
  }

  /** A referee's whistle: two close tones with a trill. */
  private whistle(gain: number, length: number, delay: number) {
    const start = this.ctx.currentTime + delay;
    const env = this.ctx.createGain();
    env.gain.setValueAtTime(0, start);
    env.gain.linearRampToValueAtTime(gain * 0.25, start + 0.02);
    env.gain.setValueAtTime(gain * 0.25, start + length - 0.05);
    env.gain.linearRampToValueAtTime(0, start + length);
    const trill = this.ctx.createOscillator();
    trill.frequency.value = 28;
    const trillDepth = this.ctx.createGain();
    trillDepth.gain.value = gain * 0.08;
    trill.connect(trillDepth).connect(env.gain);
    env.connect(this.effects);
    for (const frequency of [2850, 3120]) {
      const osc = this.ctx.createOscillator();
      osc.frequency.value = frequency;
      osc.connect(env);
      osc.start(start);
      osc.stop(start + length);
    }
    trill.start(start);
    trill.stop(start + length);
  }

  /** The crowd rising over `length` seconds as a play develops. */
  private swell(gain: number, length: number) {
    const now = this.ctx.currentTime;
    const noise = this.source(true);
    const band = this.ctx.createBiquadFilter();
    band.type = "bandpass";
    band.frequency.setValueAtTime(700, now);
    band.frequency.linearRampToValueAtTime(1100, now + length);
    const env = this.ctx.createGain();
    env.gain.setValueAtTime(0.001, now);
    env.gain.exponentialRampToValueAtTime(gain * 0.5, now + length);
    env.gain.exponentialRampToValueAtTime(0.001, now + length + 0.6);
    noise.connect(band).connect(env).connect(this.crowd);
    noise.start(now);
    noise.stop(now + length + 0.7);
  }

  /** A crowd's reaction: a cheer (bright) or a groan (falling and dark). */
  private roar(gain: number, from: number, to: number, length: number) {
    const now = this.ctx.currentTime;
    const noise = this.source(true);
    const band = this.ctx.createBiquadFilter();
    band.type = "bandpass";
    band.Q.value = 0.7;
    band.frequency.setValueAtTime(from, now);
    band.frequency.exponentialRampToValueAtTime(to, now + length);
    const env = this.ctx.createGain();
    env.gain.setValueAtTime(0.001, now);
    env.gain.exponentialRampToValueAtTime(gain * 0.7, now + 0.25);
    env.gain.setValueAtTime(gain * 0.7, now + length * 0.5);
    env.gain.exponentialRampToValueAtTime(0.001, now + length);
    noise.connect(band).connect(env).connect(this.crowd);
    noise.start(now);
    noise.stop(now + length + 0.05);
  }
}
