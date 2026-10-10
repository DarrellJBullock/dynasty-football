"use client";

import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useMemo, useRef, useState } from "react";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { TeamCrest } from "@/components/ui/TeamCrest";
import { api } from "@/lib/api";
import {
  addablePlayers,
  moveItem,
  replaceSlotOrder,
  rowStatus,
  SLOT_NAMES,
  startingSlots,
  UNITS,
} from "@/lib/depthChart";
import type { DepthChart, DepthSlot, PlayerSummary, Position, Unit } from "@/lib/types";
import { DepthRow } from "./DepthRow";

export function DepthChartEditor({ initialChart }: { initialChart: DepthChart }) {
  const [chart, setChart] = useState(initialChart);
  const [unit, setUnit] = useState<Unit>("offense");
  const [selected, setSelected] = useState<Position>("QB");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Only the newest request may update state, so fast consecutive edits can't race.
  const latestRequest = useRef(0);

  const team = chart.team;
  const starters = useMemo(() => startingSlots(chart), [chart]);
  const slot = chart.slots.find((s) => s.slot === selected)!;
  const unitSlots = chart.slots.filter((s) => s.unit === unit);

  async function save(request: () => Promise<DepthChart>, optimistic?: DepthChart) {
    const previous = chart;
    const id = ++latestRequest.current;
    if (optimistic) setChart(optimistic);
    setSaving(true);
    setError(null);
    try {
      const next = await request();
      if (id === latestRequest.current) setChart(next);
    } catch (e) {
      if (id === latestRequest.current) {
        setChart(previous);
        setError((e as Error).message);
      }
    } finally {
      if (id === latestRequest.current) setSaving(false);
    }
  }

  function saveOrder(players: PlayerSummary[]) {
    return save(
      () => api.setDepthSlot(team.id, slot.slot, players.map((p) => p.id)),
      replaceSlotOrder(chart, slot.slot, players),
    );
  }

  function selectUnit(next: Unit) {
    setUnit(next);
    setSelected(chart.slots.find((s) => s.unit === next)!.slot);
  }

  return (
    <div
      className="mx-auto max-w-7xl space-y-6"
      style={{ "--team-primary": team.primary_color } as React.CSSProperties}
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-4">
          <TeamCrest team={team} size={52} />
          <div>
            <div className="eyebrow text-gold">Depth chart</div>
            <h1 className="font-display text-4xl font-bold uppercase tracking-wide">{team.full_name}</h1>
          </div>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={saving || !chart.slots.some((s) => s.customized)}
          onClick={() => save(() => api.resetDepthChart(team.id))}
        >
          Reset all to OVR order
        </button>
      </div>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Team ratings">
        {(
          [
            ["Team OVR", team.ratings.overall],
            ["Offense", team.ratings.offense],
            ["Defense", team.ratings.defense],
            ["Special Teams", team.ratings.special_teams],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="panel flex items-center justify-between px-4 py-3">
            <dt className="eyebrow">{label}</dt>
            <dd>
              <OvrBadge value={value} size="md" label={`${label} ${value}`} />
            </dd>
          </div>
        ))}
      </dl>

      {error && (
        <div role="alert" className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
          Couldn&apos;t save the depth chart: {error}
        </div>
      )}

      <div role="tablist" aria-label="Unit" className="flex gap-1">
        {UNITS.map(({ unit: u, label }) => (
          <button
            key={u}
            type="button"
            role="tab"
            aria-selected={unit === u}
            onClick={() => selectUnit(u)}
            className={`rounded-md px-3 py-1.5 font-display text-sm font-semibold uppercase tracking-wide ${
              unit === u ? "bg-gold text-ink-950" : "text-mist hover:bg-white/5 hover:text-chalk"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <nav aria-label="Positions" className="panel h-fit p-2">
          <ul className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-1">
            {unitSlots.map((s) => (
              <li key={s.slot}>
                <SlotButton
                  slot={s}
                  active={s.slot === selected}
                  onSelect={() => setSelected(s.slot)}
                />
              </li>
            ))}
          </ul>
        </nav>

        <SlotEditor
          key={slot.slot}
          chart={chart}
          slot={slot}
          starters={starters}
          saving={saving}
          onReorder={saveOrder}
          onReset={() => save(() => api.resetDepthSlot(team.id, slot.slot))}
        />
      </div>
    </div>
  );
}

function SlotButton({ slot, active, onSelect }: { slot: DepthSlot; active: boolean; onSelect: () => void }) {
  const fielded = slot.players.filter((p) => slot.starter_ids.includes(p.id));
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors ${
        active ? "bg-white/[0.07] shadow-[inset_2px_0_0_0_var(--color-gold)]" : "hover:bg-white/[0.04]"
      }`}
    >
      <span className="w-9 font-display text-lg font-bold">{slot.slot}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs text-mist">
          {SLOT_NAMES[slot.slot]}
          {slot.customized && <span className="ml-1.5 text-gold" title="Custom order">●</span>}
        </span>
        <span className="hidden truncate text-sm lg:block">
          {fielded.length
            ? fielded.map((p) => p.last_name).join(", ")
            : slot.starters
              ? <span className="text-rose-300">No starter</span>
              : <span className="text-mist">{slot.players.length} on roster</span>}
        </span>
      </span>
      {fielded[0] && <OvrBadge value={fielded[0].overall} />}
    </button>
  );
}

function SlotEditor({
  chart,
  slot,
  starters,
  saving,
  onReorder,
  onReset,
}: {
  chart: DepthChart;
  slot: DepthSlot;
  starters: Map<number, Position>;
  saving: boolean;
  onReorder: (players: PlayerSummary[]) => void;
  onReset: () => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const players = slot.players;
  const candidates = useMemo(() => addablePlayers(chart, slot), [chart, slot]);

  function onDragEnd({ active, over }: DragEndEvent) {
    if (!over || active.id === over.id) return;
    const from = players.findIndex((p) => p.id === active.id);
    const to = players.findIndex((p) => p.id === over.id);
    onReorder(moveItem(players, from, to));
  }

  return (
    <section className="panel p-5" aria-label={`${SLOT_NAMES[slot.slot]} depth chart`}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-bold uppercase tracking-wide">{SLOT_NAMES[slot.slot]}</h2>
          <p className="text-xs text-mist">
            {slot.starters
              ? `${slot.starters} starter${slot.starters > 1 ? "s" : ""} · drag or use the arrows to reorder`
              : "Reserve position — no base-formation starters"}
            {saving && <span className="ml-2 text-gold">Saving…</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            aria-label={`Add a player to ${slot.slot}`}
            className="field-input w-56"
            value=""
            disabled={saving}
            onChange={(e) => {
              const player = candidates.find((p) => p.id === Number(e.target.value));
              if (player) onReorder([...players, player]);
            }}
          >
            <option value="">+ Add player from roster…</option>
            {candidates.map((p) => (
              <option key={p.id} value={p.id}>
                {p.position} · {p.full_name} ({p.overall})
              </option>
            ))}
          </select>
          <button type="button" className="btn btn-ghost" disabled={saving || !slot.customized} onClick={onReset}>
            Reset to OVR order
          </button>
        </div>
      </header>

      {players.length === 0 ? (
        <p className="py-10 text-center text-sm text-mist">No players at this position. Add one from the roster.</p>
      ) : (
        <DndContext
          id={`depth-${slot.slot}`}
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToVerticalAxis]}
          onDragEnd={onDragEnd}
        >
          <SortableContext items={players.map((p) => p.id)} strategy={verticalListSortingStrategy}>
            <ol className="space-y-2" aria-label={`${slot.slot} depth order`}>
              {players.map((player, index) => (
                <DepthRow
                  key={player.id}
                  player={player}
                  depth={index + 1}
                  slot={slot.slot}
                  status={rowStatus(player, index, slot, starters)}
                  isFirst={index === 0}
                  isLast={index === players.length - 1}
                  disabled={saving}
                  onMove={(direction) => onReorder(moveItem(players, index, index + direction))}
                  onRemove={
                    player.position !== slot.slot
                      ? () => onReorder(players.filter((p) => p.id !== player.id))
                      : undefined
                  }
                />
              ))}
            </ol>
          </SortableContext>
        </DndContext>
      )}
    </section>
  );
}
