/**
 * The playhead shared by the 3D scene (which advances it every frame) and the controls
 * (which seek, pause and change speed). A plain mutable object, so playing a play
 * re-renders nothing. Pure.
 */
export class PlayClock {
  time = 0;
  playing = true;
  speed = 1;

  /** Moves the playhead on by `delta` seconds of real time (at the clock's speed), stopping
   * at `duration`. Returns true on the step that reaches the end. */
  advance(delta: number, duration: number): boolean {
    if (!this.playing) return false;
    this.time = Math.min(duration, this.time + Math.min(delta, 0.1) * this.speed);
    if (this.time < duration) return false;
    this.playing = false;
    return true;
  }

  seek(time: number) { this.time = time; }
  setPlaying(playing: boolean) { this.playing = playing; }
  setSpeed(speed: number) { this.speed = speed; }
}
