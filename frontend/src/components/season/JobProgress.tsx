"use client";

import type { Job } from "@/lib/types";

/** A background sim's progress bar ("Week 9 of 17"), with Stop for jobs that can stop. */
export function JobProgress({ job, onStop }: { job: Job; onStop: () => void }) {
  const percent = job.total ? Math.round((100 * job.progress) / job.total) : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <div role="progressbar" aria-label="Simulation progress" aria-valuemin={0}
        aria-valuemax={job.total} aria-valuenow={job.progress}
        aria-valuetext={`${job.label}: ${job.progress} of ${job.total}`}
        className="h-2 w-36 overflow-hidden rounded-full bg-white/[0.07]">
        <div className="h-full rounded-full bg-gold transition-[width] duration-300"
          style={{ width: `${percent}%` }} />
      </div>
      <span className="tabular-nums text-chalk">{job.label}</span>
      {job.cancellable && (job.cancel_requested ? (
        <span className="text-mist">Stopping after this one…</span>
      ) : (
        <button type="button" className="btn btn-ghost px-2 py-0.5 text-xs" onClick={onStop}>
          Stop
        </button>
      ))}
    </div>
  );
}
