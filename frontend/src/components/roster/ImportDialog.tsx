"use client";

import { useState } from "react";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { api, importTemplateUrl } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { ImportFormat, ImportMode, ImportPreview, ImportResult, ImportRow } from "@/lib/types";
import { Dialog } from "@/components/ui/Dialog";

const ACCEPT = ".csv,.xlsx,.json";
const TEMPLATES: { format: ImportFormat; label: string }[] = [
  { format: "csv", label: "CSV" },
  { format: "xlsx", label: "Excel" },
  { format: "json", label: "JSON" },
];

export function ImportDialog({
  teamId,
  rosterCount,
  onImported,
  onClose,
}: {
  teamId: number;
  rosterCount: number;
  onImported: (result: ImportResult) => Promise<void> | void;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<ImportMode>("append");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipInvalid, setSkipInvalid] = useState(false);
  const [problemsOnly, setProblemsOnly] = useState(false);
  const [dragging, setDragging] = useState(false);

  async function runPreview(nextFile: File, nextMode: ImportMode) {
    setFile(nextFile);
    setMode(nextMode);
    setLoading(true);
    setError(null);
    setSkipInvalid(false);
    try {
      setPreview(await api.previewImport(teamId, nextFile, nextMode));
    } catch (e) {
      setPreview(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function commit() {
    if (!file) return;
    setCommitting(true);
    setError(null);
    try {
      await onImported(await api.commitImport(teamId, file, mode, skipInvalid));
    } catch (e) {
      setError((e as Error).message);
      setCommitting(false);
    }
  }

  const summary = preview?.summary;
  const canImport =
    !!preview && !loading && summary!.valid > 0 && (summary!.errors === 0 || skipInvalid);
  const rows = preview?.rows.filter((r) => !problemsOnly || r.status !== "ok") ?? [];

  return (
    <Dialog title="Import roster" onClose={onClose} size="lg">
      <div className="space-y-5">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const dropped = e.dataTransfer.files[0];
              if (dropped) void runPreview(dropped, mode);
            }}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors ${
              dragging ? "border-gold bg-gold/5" : "border-white/10 hover:border-white/25"
            }`}
          >
            <svg viewBox="0 0 24 24" className="h-7 w-7 text-mist" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
              <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {file ? (
              <span className="text-sm">
                <span className="font-medium">{file.name}</span>
                <span className="text-mist"> · {Math.max(1, Math.round(file.size / 1024))} KB · choose another</span>
              </span>
            ) : (
              <span className="text-sm">
                <span className="font-medium text-gold">Choose a file</span>
                <span className="text-mist"> or drag it here</span>
              </span>
            )}
            <span className="text-xs text-mist">CSV, Excel (.xlsx) or JSON · up to 2 MB</span>
            <input
              type="file"
              accept={ACCEPT}
              className="sr-only"
              aria-label="Roster file"
              onChange={(e) => {
                const chosen = e.target.files?.[0];
                if (chosen) void runPreview(chosen, mode);
                e.target.value = "";
              }}
            />
          </label>

          <fieldset className="space-y-2">
            <legend className="eyebrow mb-2">Import mode</legend>
            {(
              [
                ["append", "Add to roster", `Keep your ${rosterCount} players and fill open spots.`],
                ["replace", "Replace roster", `Release all ${rosterCount} current players to free agency.`],
              ] as const
            ).map(([value, label, hint]) => (
              <label
                key={value}
                className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 ${
                  mode === value ? "border-gold/50 bg-gold/[0.05]" : "border-white/10 hover:border-white/20"
                }`}
              >
                <input
                  type="radio"
                  name="import-mode"
                  value={value}
                  checked={mode === value}
                  onChange={() => (file ? void runPreview(file, value) : setMode(value))}
                  className="mt-1 accent-[var(--color-gold)]"
                />
                <span>
                  <span className="block text-sm font-medium">{label}</span>
                  <span className="block text-xs text-mist">{hint}</span>
                </span>
              </label>
            ))}
            <p className="pt-1 text-xs text-mist">
              Template:{" "}
              {TEMPLATES.map(({ format, label }, i) => (
                <span key={format}>
                  {i > 0 && " · "}
                  <a href={importTemplateUrl(format)} download className="text-gold hover:underline">
                    {label}
                  </a>
                </span>
              ))}
            </p>
          </fieldset>
        </div>

        {loading && <p className="text-sm text-mist">Checking file…</p>}
        {error && (
          <p role="alert" className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        )}

        {preview && summary && !loading && (
          <section aria-label="Import preview" className="space-y-4">
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Rows" value={summary.total} />
              <Stat label="Ready" value={summary.valid} tone="text-emerald-300" />
              <Stat label="Warnings" value={summary.warnings} tone={summary.warnings ? "text-amber-300" : ""} />
              <Stat label="Errors" value={summary.errors} tone={summary.errors ? "text-rose-300" : ""} />
            </dl>
            <p className="text-sm text-mist">
              Roster {preview.roster_before} → <span className="text-chalk">{preview.roster_after}</span>/
              {preview.roster_max}
              {preview.released > 0 && <> · {preview.released} released to free agency</>} · Payroll{" "}
              <span className={preview.payroll_after > preview.salary_cap ? "text-rose-300" : "text-chalk"}>
                {formatMoney(preview.payroll_after)}
              </span>{" "}
              of {formatMoney(preview.salary_cap)} cap
            </p>
            {preview.file_warnings.length > 0 && (
              <ul className="space-y-1 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-sm text-amber-200">
                {preview.file_warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}

            <div className="flex items-center justify-between">
              <h3 className="eyebrow">Players</h3>
              <label className="flex items-center gap-2 text-xs text-mist">
                <input
                  type="checkbox"
                  checked={problemsOnly}
                  onChange={(e) => setProblemsOnly(e.target.checked)}
                  className="accent-[var(--color-gold)]"
                />
                Only rows with issues
              </label>
            </div>
            <div className="max-h-80 overflow-auto rounded-lg border border-white/5">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="sticky top-0 bg-ink-900">
                  <tr className="text-left text-[11px] uppercase tracking-wider text-mist">
                    <th className="px-3 py-2 font-medium">Row</th>
                    <th className="px-3 py-2 font-medium">Player</th>
                    <th className="px-3 py-2 font-medium">Pos</th>
                    <th className="px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 text-center font-medium">OVR</th>
                    <th className="px-3 py-2 text-right font-medium">Salary</th>
                    <th className="px-3 py-2 font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <PreviewRow key={row.row_number} row={row} />
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-6 text-center text-mist">
                        No issues found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-white/5 pt-4">
          {summary && summary.errors > 0 && summary.valid > 0 && (
            <label className="mr-auto flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={skipInvalid}
                onChange={(e) => setSkipInvalid(e.target.checked)}
                className="accent-[var(--color-gold)]"
              />
              Skip {plural(summary.errors, "row")} with errors
            </label>
          )}
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${mode === "replace" ? "btn-danger" : "btn-primary"}`}
            disabled={!canImport || committing}
            onClick={commit}
          >
            {committing
              ? "Importing…"
              : mode === "replace"
                ? `Replace roster with ${plural(summary?.valid ?? 0, "player")}`
                : `Import ${plural(summary?.valid ?? 0, "player")}`}
          </button>
        </div>
      </div>
    </Dialog>
  );
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function Stat({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-3 py-2">
      <dt className="text-[10px] uppercase tracking-wider text-mist">{label}</dt>
      <dd className={`stat-number text-2xl ${tone}`}>{value}</dd>
    </div>
  );
}

const STATUS_DOT: Record<ImportRow["status"], string> = {
  ok: "bg-emerald-400",
  warning: "bg-amber-400",
  error: "bg-rose-400",
};

function PreviewRow({ row }: { row: ImportRow }) {
  const name = `${row.first_name} ${row.last_name}`.trim() || "—";
  return (
    <tr className="border-t border-white/5 align-top" data-testid="import-row" data-status={row.status}>
      <td className="px-3 py-2 tabular-nums text-mist">
        <span className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${STATUS_DOT[row.status]}`} aria-label={row.status} />
          {row.row_number}
        </span>
      </td>
      <td className="px-3 py-2 font-medium">{name}</td>
      <td className="px-3 py-2 font-display font-semibold">{row.position ?? "—"}</td>
      <td className="px-3 py-2 tabular-nums">{row.jersey_number ?? "—"}</td>
      <td className="px-3 py-2 text-center">{row.overall !== null ? <OvrBadge value={row.overall} /> : "—"}</td>
      <td className="px-3 py-2 text-right tabular-nums">{row.salary !== null ? formatMoney(row.salary) : "—"}</td>
      <td className="px-3 py-2 text-xs">
        {row.messages.map((m) => (
          <div key={m.message} className={m.level === "error" ? "text-rose-300" : "text-amber-300"}>
            {m.message}
          </div>
        ))}
      </td>
    </tr>
  );
}
