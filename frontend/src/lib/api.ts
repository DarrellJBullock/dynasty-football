import type {
  Dashboard,
  DepthChart,
  DivisionStandings,
  Franchise,
  PlayerCreate,
  PlayerDetail,
  PlayerSummary,
  PlayerUpdate,
  Position,
  TeamDetail,
} from "@/lib/types";

const DEFAULT_API_URL = "http://localhost:8000";

/** Server components read API_URL; the browser uses the inlined NEXT_PUBLIC_API_URL. */
export function apiBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL;
  }
  return process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the game server at ${apiBaseUrl()}.`);
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      // FastAPI validation errors: [{loc: [...], msg: "..."}]
      return body.detail
        .map((d: { loc?: unknown[]; msg: string }) => `${d.loc?.slice(1).join(".")}: ${d.msg}`)
        .join("; ");
    }
  } catch {
    // fall through
  }
  return `Request failed (${response.status})`;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  franchise: () => request<Franchise>("/franchise"),
  dashboard: () => request<Dashboard>("/franchise/dashboard"),
  team: (teamId: number) => request<TeamDetail>(`/teams/${teamId}`),
  roster: (teamId: number) => request<PlayerSummary[]>(`/teams/${teamId}/roster`),
  leagueTeams: (leagueId: number) => request<TeamDetail[]>(`/leagues/${leagueId}/teams`),
  standings: (leagueId: number) => request<DivisionStandings[]>(`/leagues/${leagueId}/standings`),
  freeAgents: (leagueId: number) => request<PlayerSummary[]>(`/leagues/${leagueId}/free-agents`),
  player: (playerId: number) => request<PlayerDetail>(`/players/${playerId}`),
  updatePlayer: (playerId: number, update: PlayerUpdate) =>
    request<PlayerDetail>(`/players/${playerId}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    }),
  releasePlayer: (playerId: number) => post<PlayerDetail>(`/players/${playerId}/release`),
  signPlayer: (teamId: number, playerId: number, years = 1) =>
    post<PlayerDetail>(`/teams/${teamId}/signings`, { player_id: playerId, years }),
  createPlayer: (teamId: number, player: PlayerCreate) =>
    post<PlayerDetail>(`/teams/${teamId}/players`, player),
  depthChart: (teamId: number) => request<DepthChart>(`/teams/${teamId}/depth-chart`),
  setDepthSlot: (teamId: number, slot: Position, playerIds: number[]) =>
    request<DepthChart>(`/teams/${teamId}/depth-chart/${slot}`, {
      method: "PUT",
      body: JSON.stringify({ player_ids: playerIds }),
    }),
  resetDepthSlot: (teamId: number, slot: Position) =>
    request<DepthChart>(`/teams/${teamId}/depth-chart/${slot}`, { method: "DELETE" }),
  resetDepthChart: (teamId: number) =>
    request<DepthChart>(`/teams/${teamId}/depth-chart`, { method: "DELETE" }),
};

export type Result<T> = { ok: true; data: T } | { ok: false; error: unknown };

/** Await a loader and capture failure as a value, so pages can render an error state. */
export async function attempt<T>(load: () => Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, data: await load() };
  } catch (error) {
    return { ok: false, error };
  }
}
