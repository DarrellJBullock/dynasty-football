import Link from "next/link";
import type { LockerRoom } from "@/lib/types";
import { MoodMeter } from "./MoodMeter";

const ORDER = ["Happy", "Content", "Unhappy", "Miserable"];

/** The team's mood at a glance: the average, how many are happy to miserable, and the
 * unhappiest players with what's eating them. */
export function LockerRoomPanel({ room }: { room: LockerRoom }) {
  return (
    <section className="panel space-y-3 p-5" aria-label="Locker room">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="eyebrow">Locker room</h2>
        <p className="text-xs text-mist">
          {ORDER.map((name) => `${room.counts[name] ?? 0} ${name.toLowerCase()}`).join(" · ")}
        </p>
      </div>
      <div>
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-mist">Average mood</span>
          <span className="stat-number text-xl">{room.average}</span>
        </div>
        <MoodMeter label="Average mood" value={room.average} />
      </div>
      {room.unhappiest.length > 0 && (
        <ul aria-label="Least happy" className="space-y-1 text-sm">
          {room.unhappiest.map((p) => (
            <li key={p.player_id} className="flex flex-wrap items-center gap-2">
              <span className="w-8 text-xs text-mist">{p.position}</span>
              <Link href={`/players/${p.player_id}`} className="hover:text-gold">{p.name}</Link>
              <span className="text-xs text-mist">{p.reason ?? ""}</span>
              <span className="ml-auto tabular-nums text-xs">{p.label} · {p.mood}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
