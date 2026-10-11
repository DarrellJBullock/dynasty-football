"use client";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { OvrBadge } from "@/components/ui/OvrBadge";
import { injuryDetail, injuryLabel } from "@/lib/format";
import type { RowStatus } from "@/lib/depthChart";
import type { PlayerSummary, Position } from "@/lib/types";

export function DepthRow({
  player,
  depth,
  slot,
  status,
  isFirst,
  isLast,
  disabled,
  onMove,
  onRemove,
}: {
  player: PlayerSummary;
  depth: number;
  slot: Position;
  status: RowStatus;
  isFirst: boolean;
  isLast: boolean;
  disabled: boolean;
  onMove: (direction: -1 | 1) => void;
  onRemove?: () => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: player.id, disabled });
  const crossListed = player.position !== slot;

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      data-testid="depth-row"
      aria-label={`${depth}. ${player.full_name}`}
      className={`group flex items-center gap-3 rounded-xl border px-3 py-2.5 ${
        isDragging
          ? "relative z-10 border-gold/50 bg-ink-700 shadow-2xl"
          : status.kind === "starter"
            ? "border-gold/20 bg-gold/[0.04]"
            : "border-white/5 bg-white/[0.02]"
      }`}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        disabled={disabled}
        aria-label={`Drag to reorder ${player.full_name}`}
        className="cursor-grab touch-none rounded p-1 text-mist hover:text-chalk active:cursor-grabbing disabled:cursor-not-allowed"
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4" fill="currentColor" aria-hidden>
          {[3, 8, 13].flatMap((y) => [5, 11].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.4" />))}
        </svg>
      </button>

      <span className="stat-number w-6 text-center text-lg text-mist">{depth}</span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium">{player.full_name}</span>
          {crossListed && (
            <span className="rounded bg-sky-400/10 px-1.5 text-[10px] font-semibold uppercase text-sky-300">
              {player.position}
            </span>
          )}
          {player.injury_status !== "healthy" && (
            <span title={injuryDetail(player)}
              className="rounded bg-rose-500/15 px-1.5 text-[10px] font-semibold uppercase text-rose-300">
              {injuryLabel(player.injury_status)}
            </span>
          )}
        </div>
        <div className="text-xs text-mist">
          #{player.jersey_number} · Age {player.age}
          <StatusNote status={status} />
        </div>
      </div>

      <OvrBadge value={player.overall} size="md" />

      <div className="flex items-center gap-0.5">
        <IconButton label={`Move ${player.full_name} up`} disabled={disabled || isFirst} onClick={() => onMove(-1)}>
          <path d="m4 10 4-4 4 4" />
        </IconButton>
        <IconButton label={`Move ${player.full_name} down`} disabled={disabled || isLast} onClick={() => onMove(1)}>
          <path d="m4 6 4 4 4-4" />
        </IconButton>
        {onRemove && (
          <IconButton label={`Remove ${player.full_name} from ${slot}`} disabled={disabled} onClick={onRemove}>
            <path d="m4.5 4.5 7 7m0-7-7 7" />
          </IconButton>
        )}
      </div>
    </li>
  );
}

function StatusNote({ status }: { status: RowStatus }) {
  switch (status.kind) {
    case "starter":
      return <span className="ml-2 font-semibold uppercase tracking-wider text-gold">Starter</span>;
    case "injured":
      return <span className="ml-2 text-rose-300">Injured — not starting</span>;
    case "starting-elsewhere":
      return <span className="ml-2 text-amber-300">Starting at {status.slot}</span>;
    default:
      return null;
  }
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded-md p-1.5 text-mist hover:bg-white/[0.06] hover:text-chalk disabled:pointer-events-none disabled:opacity-25"
    >
      <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        {children}
      </svg>
    </button>
  );
}
