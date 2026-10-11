"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Job, JobKind } from "@/lib/types";

const POLL_MS = 500;

export const jobActive = (job: Job | null | undefined): job is Job =>
  job != null && (job.status === "queued" || job.status === "running");

/**
 * Runs a background sim (`/api/leagues/{id}/jobs`): starts it, polls its progress until it
 * ends, then calls `onEnd` with the finished job (done, failed or cancelled). Picks up
 * `initial`, a job already running in the league, so leaving the page and coming back
 * shows it again.
 */
export function useJob(initial: Job | null | undefined, onEnd: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(jobActive(initial) ? initial : null);
  const [retry, setRetry] = useState(0);
  const onEndRef = useRef(onEnd);
  useEffect(() => {
    onEndRef.current = onEnd;
  });

  const active = jobActive(job);
  useEffect(() => {
    if (!active || !job) return;
    let stopped = false;
    const timer = setTimeout(async () => {
      try {
        const next = await api.job(job.id);
        if (stopped) return;
        setJob(next);
        if (!jobActive(next)) onEndRef.current(next);
      } catch {
        if (!stopped) setRetry((n) => n + 1); // a blip: look again shortly
      }
    }, POLL_MS);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [active, job, retry]);

  function settle(next: Job) {
    setJob(next);
    if (!jobActive(next)) onEndRef.current(next);
  }

  return {
    /** The job while it's queued or running. */
    job: active ? job : null,
    /** Start a job (errors, like a 409 for a league that's busy, are thrown). */
    start: async (leagueId: number, kind: JobKind) => settle(await api.startJob(leagueId, kind)),
    /** Ask the job to stop after its current week (round, day). */
    cancel: async () => {
      if (job) settle(await api.cancelJob(job.id));
    },
  };
}
