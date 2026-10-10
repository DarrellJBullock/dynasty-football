"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/ui/Dialog";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import type { TeamIdentity, TeamSummary } from "@/lib/types";

type Editable = TeamIdentity & Pick<TeamSummary, "id" | "full_name">;

/** Pencil button that opens a dialog to edit a team's identity, then refreshes the page. */
export function TeamEditButton({ team }: { team: Editable }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Edit ${team.full_name}`}
        title={`Edit ${team.full_name}`}
        className="rounded p-1 text-mist opacity-60 hover:bg-white/[0.06] hover:text-chalk hover:opacity-100"
      >
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
          <path d="M11 2.5 13.5 5 6 12.5H3.5V10L11 2.5Z" strokeLinejoin="round" />
        </svg>
      </button>
      {open && <TeamEditDialog team={team} onClose={() => setOpen(false)} />}
    </>
  );
}

export function TeamEditDialog({ team, onClose }: { team: Editable; onClose: () => void }) {
  const router = useRouter();
  const [form, setForm] = useState<TeamIdentity>({
    city: team.city,
    nickname: team.nickname,
    abbreviation: team.abbreviation,
    primary_color: team.primary_color,
    secondary_color: team.secondary_color,
    stadium: team.stadium,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.updateTeam(team.id, form);
      onClose();
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  }

  const text = (key: "city" | "nickname" | "stadium", label: string, max: number) => (
    <label className="block space-y-1">
      <span className="text-xs text-mist">{label}</span>
      <input className="field-input" required maxLength={max} value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </label>
  );

  return (
    <Dialog title="Edit team" onClose={onClose}>
      <form onSubmit={save} className="space-y-5">
        <div className="flex items-center gap-4 rounded-xl bg-white/[0.03] p-4">
          <TeamCrest team={{ ...form, full_name: `${form.city} ${form.nickname}` }} size={56} />
          <div>
            <div className="font-display text-sm uppercase text-mist">{form.city || "City"}</div>
            <div className="font-display text-3xl font-bold uppercase leading-none">{form.nickname || "Nickname"}</div>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {text("city", "City", 60)}
          {text("nickname", "Nickname", 60)}
          <label className="block space-y-1">
            <span className="text-xs text-mist">Abbreviation</span>
            <input className="field-input uppercase" required pattern="[A-Za-z0-9]{2,4}" maxLength={4}
              value={form.abbreviation}
              onChange={(e) => setForm({ ...form, abbreviation: e.target.value.toUpperCase() })} />
          </label>
          {text("stadium", "Stadium", 80)}
          {(["primary_color", "secondary_color"] as const).map((key) => (
            <label key={key} className="flex items-center gap-3">
              <input type="color" value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value.toUpperCase() })}
                className="h-10 w-12 cursor-pointer rounded border border-white/10 bg-transparent" />
              <span className="text-sm">
                {key === "primary_color" ? "Primary color" : "Secondary color"}
                <span className="block font-mono text-xs text-mist">{form[key]}</span>
              </span>
            </label>
          ))}
        </div>
        {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save team"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
