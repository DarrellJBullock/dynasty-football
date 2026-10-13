import type { Metadata } from "next";
import { Suspense } from "react";
import { JoinLeague } from "@/components/members/JoinLeague";

export const metadata: Metadata = { title: "Join a league" };

export default function JoinPage() {
  // (The form reads ?token= from the URL, which is only known at request time. Signed-out
  // visitors are sent to sign in first, and come back here.)
  return (
    <Suspense>
      <JoinLeague />
    </Suspense>
  );
}
