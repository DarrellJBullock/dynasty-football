"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { RatingBar } from "@/components/ui/RatingBar";
import { useModal } from "@/components/ui/useModal";
import { api } from "@/lib/api";
import { ATTRIBUTE_CATEGORIES } from "@/lib/attributes";
import {
  formatAttribute,
  formatHeight,
  formatMoney,
  injuryLabel,
  yearsRemaining,
} from "@/lib/format";
import {
  DEVELOPMENT_TRAITS,
  INJURY_STATUSES,
  POSITIONS,
  type PlayerDetail,
  type PlayerUpdate,
} from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; player: PlayerDetail };

export function PlayerPanel({
  playerId,
  seasonYear,
  onClose,
  onUpdated,
  onReleased,
}: {
  playerId: number;
  seasonYear: number;
  onClose: () => void;
  onUpdated: (player: PlayerDetail) => void;
  onReleased: (player: PlayerDetail) => void;
}) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [editing, setEditing] = useState(false);
  // Remember which player the panel was opened for, so switching players resets it.
  const [shownId, setShownId] = useState(playerId);
  if (shownId !== playerId) {
    setShownId(playerId);
    setState({ status: "loading" });
    setEditing(false);
  }

  useEffect(() => {
    let cancelled = false;
    api
      .player(playerId)
      .then((player) => !cancelled && setState({ status: "ready", player }))
      .catch((e: Error) => !cancelled && setState({ status: "error", message: e.message }));
    return () => {
      cancelled = true;
    };
  }, [playerId]);

  const modalRef = useModal<HTMLElement>(onClose);

  // Portal to <body> so no ancestor's backdrop-filter can trap the fixed overlay.
  return createPortal(
    <>
      <div className="fixed inset-0 z-40 bg-ink-950/60 backdrop-blur-[2px]" onClick={onClose} />
      <aside
        ref={modalRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Player details"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l outline-none border-white/10 bg-ink-900 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <span className="eyebrow">{editing ? "Edit player" : "Player card"}</span>
          <button type="button" onClick={onClose} className="btn btn-ghost px-2 py-1" aria-label="Close">
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 pt-5">
          {state.status === "loading" && <p className="text-sm text-mist">Loading…</p>}
          {state.status === "error" && <p className="text-sm text-rose-300">{state.message}</p>}
          {state.status === "ready" &&
            (editing ? (
              <PlayerEditForm
                player={state.player}
                onCancel={() => setEditing(false)}
                onSaved={(player) => {
                  setState({ status: "ready", player });
                  setEditing(false);
                  onUpdated(player);
                }}
              />
            ) : (
              <PlayerCard
                player={state.player}
                seasonYear={seasonYear}
                onEdit={() => setEditing(true)}
                onReleased={onReleased}
              />
            ))}
        </div>
      </aside>
    </>,
    document.body,
  );
}

function PlayerCard({
  player,
  seasonYear,
  onEdit,
  onReleased,
}: {
  player: PlayerDetail;
  seasonYear: number;
  onEdit: () => void;
  onReleased: (player: PlayerDetail) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const keys = new Set(Object.keys(player.key_ratings));

  async function release() {
    setBusy(true);
    setError(null);
    try {
      onReleased(await api.releasePlayer(player.id));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div className="stat-number text-5xl text-mist/60">#{player.jersey_number}</div>
        <div className="min-w-0 flex-1">
          <div className="text-sm text-mist">{player.first_name}</div>
          <h2 className="font-display text-3xl font-bold uppercase leading-none">
            {player.last_name}
          </h2>
          <div className="mt-1 text-sm text-mist">
            {player.position} · {player.college}
          </div>
        </div>
        <OvrBadge value={player.overall} size="lg" />
      </div>

      <dl className="grid grid-cols-3 gap-3 text-center">
        {[
          ["Age", player.age],
          ["Height", formatHeight(player.height_in)],
          ["Weight", `${player.weight_lb} lb`],
          ["Potential", player.potential],
          ["Exp", player.years_pro ? `${player.years_pro} yr` : "Rookie"],
          ["Status", injuryLabel(player.injury_status)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg bg-white/[0.03] px-2 py-2.5">
            <dt className="text-[10px] uppercase tracking-wider text-mist">{label}</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="rounded-lg border border-white/5 p-3 text-sm">
        <div className="eyebrow mb-1">Contract</div>
        {player.contract ? (
          <div className="flex justify-between">
            <span>{formatMoney(player.contract.salary)} / yr</span>
            <span className="text-mist">
              {yearsRemaining(player.contract.end_year, seasonYear)} yr left · thru{" "}
              {player.contract.end_year}
            </span>
          </div>
        ) : (
          <span className="text-mist">Free agent</span>
        )}
      </div>

      <div className="space-y-5">
        {ATTRIBUTE_CATEGORIES.map((category) => (
          <div key={category.label}>
            <div className="eyebrow mb-2">{category.label}</div>
            <div className="grid grid-cols-2 gap-x-5 gap-y-2.5">
              {category.attributes.map((name) => (
                <RatingBar
                  key={name}
                  label={formatAttribute(name)}
                  value={player.ratings[name]}
                  emphasis={keys.has(name)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-rose-300">{error}</p>}
      {player.team_id !== null && (
        <div className="sticky bottom-0 -mx-5 flex gap-2 border-t border-white/5 bg-ink-900 px-5 py-4">
          <button type="button" className="btn btn-primary flex-1" onClick={onEdit}>
            Edit player
          </button>
          {confirming ? (
            <button type="button" className="btn btn-danger" disabled={busy} onClick={release}>
              {busy ? "Releasing…" : "Confirm release"}
            </button>
          ) : (
            <button type="button" className="btn btn-danger" onClick={() => setConfirming(true)}>
              Release
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function PlayerEditForm({
  player,
  onCancel,
  onSaved,
}: {
  player: PlayerDetail;
  onCancel: () => void;
  onSaved: (player: PlayerDetail) => void;
}) {
  const [bio, setBio] = useState({
    first_name: player.first_name,
    last_name: player.last_name,
    jersey_number: player.jersey_number,
    position: player.position,
    age: player.age,
    injury_status: player.injury_status,
    development_trait: player.development_trait,
  });
  const [ratings, setRatings] = useState(player.ratings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const update: PlayerUpdate = {};
    for (const [key, value] of Object.entries(bio) as [keyof typeof bio, never][]) {
      if (player[key] !== value) (update as Record<string, unknown>)[key] = value;
    }
    const changedRatings = Object.fromEntries(
      Object.entries(ratings).filter(([name, value]) => player.ratings[name] !== value),
    );
    if (Object.keys(changedRatings).length) update.ratings = changedRatings;
    if (!Object.keys(update).length) return onCancel();

    setSaving(true);
    setError(null);
    try {
      onSaved(await api.updatePlayer(player.id, update));
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  }

  const setNumber = (key: "jersey_number" | "age") => (e: React.ChangeEvent<HTMLInputElement>) =>
    setBio({ ...bio, [key]: Number(e.target.value) });

  return (
    <form onSubmit={save} className="space-y-6">
      <div className="grid grid-cols-2 gap-3">
        <Field label="First name">
          <input
            className="field-input"
            value={bio.first_name}
            required
            maxLength={40}
            onChange={(e) => setBio({ ...bio, first_name: e.target.value })}
          />
        </Field>
        <Field label="Last name">
          <input
            className="field-input"
            value={bio.last_name}
            required
            maxLength={40}
            onChange={(e) => setBio({ ...bio, last_name: e.target.value })}
          />
        </Field>
        <Field label="Jersey #">
          <input
            className="field-input"
            type="number"
            min={0}
            max={99}
            value={bio.jersey_number}
            onChange={setNumber("jersey_number")}
          />
        </Field>
        <Field label="Position">
          <select
            className="field-input"
            value={bio.position}
            onChange={(e) => setBio({ ...bio, position: e.target.value as typeof bio.position })}
          >
            {POSITIONS.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </Field>
        <Field label="Age">
          <input className="field-input" type="number" min={18} max={50} value={bio.age} onChange={setNumber("age")} />
        </Field>
        <Field label="Status">
          <select
            className="field-input"
            value={bio.injury_status}
            onChange={(e) =>
              setBio({ ...bio, injury_status: e.target.value as typeof bio.injury_status })
            }
          >
            {INJURY_STATUSES.map((s) => (
              <option key={s} value={s}>
                {injuryLabel(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Development">
          <select
            className="field-input"
            value={bio.development_trait}
            onChange={(e) =>
              setBio({ ...bio, development_trait: e.target.value as typeof bio.development_trait })
            }
          >
            {DEVELOPMENT_TRAITS.map((t) => (
              <option key={t} value={t}>
                {formatAttribute(t)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {ATTRIBUTE_CATEGORIES.map((category) => (
        <fieldset key={category.label}>
          <legend className="eyebrow mb-2">{category.label}</legend>
          <div className="space-y-2">
            {category.attributes.map((name) => (
              <label key={name} className="grid grid-cols-[8.5rem_minmax(0,1fr)_3rem] items-center gap-3 text-xs">
                <span className="text-mist">{formatAttribute(name)}</span>
                <input
                  type="range"
                  min={0}
                  max={99}
                  value={ratings[name]}
                  onChange={(e) => setRatings({ ...ratings, [name]: Number(e.target.value) })}
                  className="accent-[var(--color-gold)]"
                  aria-label={formatAttribute(name)}
                />
                <span className="stat-number text-right text-sm">{ratings[name]}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ))}

      {error && (
        <p role="alert" className="text-sm text-rose-300">
          {error}
        </p>
      )}
      <div className="sticky bottom-0 -mx-5 flex gap-2 border-t border-white/5 bg-ink-900 px-5 py-4">
        <button type="submit" className="btn btn-primary flex-1" disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-mist">{label}</span>
      {children}
    </label>
  );
}
