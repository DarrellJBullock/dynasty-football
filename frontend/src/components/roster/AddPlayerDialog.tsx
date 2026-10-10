"use client";

import { useState } from "react";
import { POSITIONS, type PlayerCreate, type Position } from "@/lib/types";
import { Dialog } from "@/components/ui/Dialog";

/** Create a custom player with default (50) ratings; fine-tune them afterwards in the editor. */
export function AddPlayerDialog({
  onCreate,
  onClose,
}: {
  onCreate: (player: PlayerCreate) => Promise<void>;
  onClose: () => void;
}) {
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    position: "QB" as Position,
    jersey_number: 0,
    age: 22,
    college: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onCreate({ ...form, college: form.college.trim() || "Undrafted" });
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <Dialog title="Create player" onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-4">
        <label className="space-y-1">
          <span className="text-xs text-mist">First name</span>
          <input
            className="field-input"
            required
            maxLength={40}
            value={form.first_name}
            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-mist">Last name</span>
          <input
            className="field-input"
            required
            maxLength={40}
            value={form.last_name}
            onChange={(e) => setForm({ ...form, last_name: e.target.value })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-mist">Position</span>
          <select
            className="field-input"
            value={form.position}
            onChange={(e) => setForm({ ...form, position: e.target.value as Position })}
          >
            {POSITIONS.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-mist">Jersey #</span>
          <input
            className="field-input"
            type="number"
            min={0}
            max={99}
            required
            value={form.jersey_number}
            onChange={(e) => setForm({ ...form, jersey_number: Number(e.target.value) })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-mist">Age</span>
          <input
            className="field-input"
            type="number"
            min={18}
            max={50}
            value={form.age}
            onChange={(e) => setForm({ ...form, age: Number(e.target.value) })}
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-mist">College</span>
          <input
            className="field-input"
            placeholder="Undrafted"
            maxLength={60}
            value={form.college}
            onChange={(e) => setForm({ ...form, college: e.target.value })}
          />
        </label>
        <p className="col-span-2 text-xs text-mist">
          All ratings start at 50. Open the player afterwards to tune attributes.
        </p>
        {error && (
          <p role="alert" className="col-span-2 text-sm text-rose-300">
            {error}
          </p>
        )}
        <div className="col-span-2 flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Creating…" : "Create player"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
