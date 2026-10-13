import type { Metadata } from "next";
import { Suspense } from "react";
import { CareerView } from "@/components/career/CareerView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Career" };

export default function CareerPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl space-y-6" aria-busy="true" aria-label="Loading your career">
          <Skeleton className="h-16 w-96" />
          <Skeleton className="h-36" />
          <Skeleton className="h-64" />
        </div>
      }
    >
      <CareerContent />
    </Suspense>
  );
}

async function CareerContent() {
  const result = await attempt(api.gmCareer);
  if (!result.ok) return <ServerError error={result.error} />;
  return <CareerView initial={result.data} />;
}
