import type { Metadata } from "next";
import { Suspense } from "react";
import { InboxView } from "@/components/inbox/InboxView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Inbox" };

export default function InboxPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-3xl" />}>
      <InboxContent />
    </Suspense>
  );
}

async function InboxContent() {
  const inbox = await attempt(api.notifications);
  if (!inbox.ok) return <ServerError error={inbox.error} />;
  // The email settings are the active league's (none without a league).
  const league = await attempt(async () => {
    const franchise = await api.franchise();
    return { franchise, settings: await api.notificationSettings(franchise.league.id) };
  });
  return (
    <InboxView initial={inbox.data} settings={league.ok ? league.data.settings : null}
      leagueId={league.ok ? league.data.franchise.league.id : null}
      leagueName={league.ok ? league.data.franchise.league.name : null} />
  );
}
