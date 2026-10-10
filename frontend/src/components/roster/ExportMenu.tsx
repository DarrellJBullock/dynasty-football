"use client";

import { useEffect, useRef, useState } from "react";
import { rosterExportUrl } from "@/lib/api";
import type { ImportFormat } from "@/lib/types";

const FORMATS: { format: ImportFormat; label: string; hint: string }[] = [
  { format: "csv", label: "CSV", hint: "Spreadsheets & text editors" },
  { format: "xlsx", label: "Excel", hint: ".xlsx workbook" },
  { format: "json", label: "JSON", hint: "Tools & scripts" },
];

/** Download the roster in the import format; exports re-import unchanged. */
export function ExportMenu({ teamId }: { teamId: number }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        className="btn btn-ghost"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        Export
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <path d="m4 6 4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Export roster"
          className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-white/10 bg-ink-800 p-1 shadow-2xl"
        >
          {FORMATS.map(({ format, label, hint }) => (
            <a
              key={format}
              role="menuitem"
              href={rosterExportUrl(teamId, format)}
              download
              onClick={() => setOpen(false)}
              className="flex flex-col rounded-lg px-3 py-2 hover:bg-white/[0.06] focus:bg-white/[0.06] focus:outline-none"
            >
              <span className="text-sm font-medium">{label}</span>
              <span className="text-xs text-mist">{hint}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
