import type { Metadata } from "next";
import { LeagueBuilder } from "@/components/leagues/LeagueBuilder";

export const metadata: Metadata = { title: "Create League" };

export default function NewLeaguePage() {
  return <LeagueBuilder />;
}
