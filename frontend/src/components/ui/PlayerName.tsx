import Link from "next/link";
import type { Site } from "@/lib/site";

/** A player's name: a link to his page in the game, plain text on a public link. */
export function PlayerName({ id, site, className, children }: {
  id: number; site?: Site; className?: string; children: React.ReactNode;
}) {
  if (site?.shared) return <span className={className?.replace(/\s*hover:\S+/g, "")}>{children}</span>;
  return <Link href={`/players/${id}`} className={className}>{children}</Link>;
}
