import { redirect } from "next/navigation";
import { gameServerUrl } from "@/lib/gameServer";
import type {
  Coaches,
  StaffMarket,
  PlayerCoaching,
  Credentials,
  TeamStaff,
  HallOfFame,
  TeamRecords,
  PublicLeague,
  ShareLink,
  Notifications,
  NotificationSettings,
  TradeOffer,
  LeagueSettings,
  Turn,
  InviteCreated,
  InvitePreview,
  MemberRole,
  Members,
  Dashboard,
  PlayoffsOut,
  LeadersOut,
  CareerOut,
  ContractTerms,
  DraftOut,
  DraftResult,
  DraftUntil,
  DynastyReport,
  FreeAgencyOut,
  FreeAgencyResult,
  FreeAgencyUntil,
  GamePlan,
  GamePlanInput,
  GamePlayback,
  Job,
  JobKind,
  Playbook,
  CoachCallIn,
  CoachState,
  NextGame,
  HistoryOut,
  NegotiationResult,
  PlayerSeasonStats,
  ProspectRow,
  TeamContracts,
  TradeCenter,
  TradeEvaluation,
  TradeProposal,
  TradeResult,
  Season,
  TeamSeasonRow,
  GameDetail,
  ScheduleWeek,
  SimulateUntil,
  SimulationResult,
  FranchiseListItem,
  LeagueCreate,
  TeamUpdate,
  DepthChart,
  ImportFormat,
  ImportMode,
  ImportPreview,
  ImportResult,
  DivisionStandings,
  Franchise,
  PlayerCreate,
  PlayerDetail,
  PlayerSummary,
  PlayerUpdate,
  Position,
  TeamDetail,
  User,
} from "@/lib/types";

/**
 * Where requests go. The browser calls the web app's own `/api` (same origin, so the
 * session cookie goes along); src/proxy.ts passes it on to the game server.
 * Server components call the game server directly (`gameServerUrl`).
 */
export function apiBaseUrl(): string {
  if (typeof window === "undefined") return gameServerUrl();
  return "";
}

/** On the server, the visitor's cookies, so the game server knows who's asking. */
async function forwardedHeaders(): Promise<Record<string, string>> {
  if (typeof window !== "undefined") return {};
  const { cookies } = await import("next/headers");
  const cookie = (await cookies()).toString();
  return cookie ? { cookie } : {};
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
    // JSON bodies are strings; FormData sets its own multipart boundary header.
    const json = typeof init?.body === "string";
    response = await fetch(`${apiBaseUrl()}/api${path}`, {
      ...init,
      headers: {
        ...(json ? { "Content-Type": "application/json" } : {}),
        ...(await forwardedHeaders()),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the game server.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  if (response.status === 204) return undefined as T;
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
  me: () => request<User>("/auth/me"),
  signIn: (credentials: Credentials) => post<User>("/auth/signin", credentials),
  signUp: (credentials: Credentials) => post<User>("/auth/signup", credentials),
  signOut: () => post<void>("/auth/signout"),
  forgotPassword: (email: string) => post<{ detail: string }>("/auth/forgot", { email }),
  resetPassword: (token: string, password: string) =>
    post<void>("/auth/reset", { token, password }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/auth/password", {
      method: "PUT",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  deleteAccount: (password: string) =>
    request<void>("/auth/account", { method: "DELETE", body: JSON.stringify({ password }) }),
  updateProfile: (displayName: string) =>
    request<User>("/auth/profile", { method: "PUT", body: JSON.stringify({ display_name: displayName }) }),
  members: (leagueId: number) => request<Members>(`/leagues/${leagueId}/members`),
  createInvite: (leagueId: number) => post<InviteCreated>(`/leagues/${leagueId}/invites`),
  revokeInvite: (leagueId: number, inviteId: number) =>
    request<void>(`/leagues/${leagueId}/invites/${inviteId}`, { method: "DELETE" }),
  setMemberRole: (leagueId: number, memberId: number, role: MemberRole) =>
    request<Members>(`/leagues/${leagueId}/members/${memberId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  removeMember: (leagueId: number, memberId: number) =>
    request<void>(`/leagues/${leagueId}/members/${memberId}`, { method: "DELETE" }),
  notifications: () => request<Notifications>("/notifications"),
  unreadCount: () => request<{ unread: number }>("/notifications/unread"),
  markRead: (ids?: number[]) => post<{ unread: number }>("/notifications/read", ids ? { ids } : {}),
  notificationSettings: (leagueId: number) =>
    request<NotificationSettings>(`/leagues/${leagueId}/notification-settings`),
  setNotificationEmail: (leagueId: number, kinds: string[]) =>
    request<NotificationSettings>(`/leagues/${leagueId}/notification-settings`, {
      method: "PUT",
      body: JSON.stringify({ email: kinds }),
    }),
  shareLeague: (leagueId: number) => post<ShareLink>(`/leagues/${leagueId}/share`),
  unshareLeague: (leagueId: number) => request<void>(`/leagues/${leagueId}/share`, { method: "DELETE" }),
  // The read-only public link: no account needed (api/public.py).
  publicLeague: (token: string) => request<PublicLeague>(`/public/${encodeURIComponent(token)}`),
  publicStandings: (token: string) =>
    request<DivisionStandings[]>(`/public/${encodeURIComponent(token)}/standings`),
  publicSchedule: (token: string, week?: number) =>
    request<ScheduleWeek>(`/public/${encodeURIComponent(token)}/schedule${week ? `?week=${week}` : ""}`),
  publicPlayoffs: (token: string) => request<PlayoffsOut>(`/public/${encodeURIComponent(token)}/playoffs`),
  publicGame: (token: string, gameId: number) =>
    request<GameDetail>(`/public/${encodeURIComponent(token)}/games/${gameId}`),
  publicPlayback: (token: string, gameId: number) =>
    request<GamePlayback>(`/public/${encodeURIComponent(token)}/games/${gameId}/playback`),
  publicLeaders: (token: string, category?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (limit) params.set("limit", String(limit));
    const query = params.size ? `?${params}` : "";
    return request<LeadersOut>(`/public/${encodeURIComponent(token)}/leaders${query}`);
  },
  publicHistory: (token: string) => request<HistoryOut>(`/public/${encodeURIComponent(token)}/history`),
  playerCoaching: (playerId: number) => request<PlayerCoaching>(`/players/${playerId}/coaching`),
  staffMarket: (leagueId: number) => request<StaffMarket>(`/leagues/${leagueId}/staff-market`),
  hireStaff: (teamId: number, staffId: number, years: number) =>
    post<TeamStaff>(`/teams/${teamId}/staff/hire`, { staff_id: staffId, years }),
  fireStaff: (staffId: number) => post<TeamStaff>(`/staff/${staffId}/fire`),
  extendStaff: (staffId: number, years: number) => post<TeamStaff>(`/staff/${staffId}/extend`, { years }),
  teamStaff: (teamId: number) => request<TeamStaff>(`/teams/${teamId}/staff`),
  coaches: (leagueId: number) => request<Coaches>(`/leagues/${leagueId}/coaches`),
  hallOfFame: (leagueId: number) => request<HallOfFame>(`/leagues/${leagueId}/hall-of-fame`),
  teamRecords: (teamId: number) => request<TeamRecords>(`/teams/${teamId}/records`),
  retireNumber: (teamId: number, playerId: number) =>
    post<TeamRecords>(`/teams/${teamId}/retired-numbers`, { player_id: playerId }),
  turn: (leagueId: number) => request<Turn>(`/leagues/${leagueId}/turn`),
  setReady: (leagueId: number, ready: boolean) =>
    request<Turn>(`/leagues/${leagueId}/ready`, { method: "PUT", body: JSON.stringify({ ready }) }),
  advanceLeague: (leagueId: number) => post<Turn>(`/leagues/${leagueId}/advance`),
  updateLeagueSettings: (leagueId: number, settings: LeagueSettings) =>
    request<Turn>(`/leagues/${leagueId}/settings`, { method: "PATCH", body: JSON.stringify(settings) }),
  previewInvite: (token: string) => post<InvitePreview>("/invites/preview", { token }),
  joinLeague: (token: string, teamId: number) =>
    post<Franchise>("/invites/join", { token, team_id: teamId }),
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
  updateTeam: (teamId: number, update: TeamUpdate) =>
    request<TeamDetail>(`/teams/${teamId}`, { method: "PATCH", body: JSON.stringify(update) }),
  leagueTemplate: (conferences: number, divisions: number, teamsPerDivision: number) =>
    request<LeagueCreate>(
      `/leagues/template?conferences=${conferences}&divisions=${divisions}&teams_per_division=${teamsPerDivision}`,
    ),
  createLeague: (spec: LeagueCreate) => post<Franchise>("/leagues", spec),
  deleteLeague: (leagueId: number) =>
    request<void>(`/leagues/${leagueId}`, { method: "DELETE" }),
  franchises: () => request<FranchiseListItem[]>("/franchises"),
  activateFranchise: (franchiseId: number) => post<Franchise>(`/franchises/${franchiseId}/activate`),
  simulate: (seasonId: number, until: SimulateUntil) =>
    post<SimulationResult>(`/seasons/${seasonId}/simulate`, { until }),
  schedule: (leagueId: number, week?: number) =>
    request<ScheduleWeek>(`/leagues/${leagueId}/schedule${week ? `?week=${week}` : ""}`),
  game: (gameId: number) => request<GameDetail>(`/games/${gameId}`),
  contracts: (teamId: number) => request<TeamContracts>(`/teams/${teamId}/contracts`),
  reSign: (playerId: number, offer: ContractTerms) =>
    post<NegotiationResult>(`/players/${playerId}/re-sign`, offer),
  freeAgency: (leagueId: number) => request<FreeAgencyOut>(`/leagues/${leagueId}/free-agency`),
  makeOffer: (playerId: number, offer: ContractTerms) =>
    post<void>(`/players/${playerId}/offer`, offer),
  withdrawOffer: (playerId: number) =>
    request<void>(`/players/${playerId}/offer`, { method: "DELETE" }),
  playFreeAgency: (seasonId: number, until: FreeAgencyUntil) =>
    post<FreeAgencyResult>(`/seasons/${seasonId}/free-agency`, { until }),
  draft: (leagueId: number) => request<DraftOut>(`/leagues/${leagueId}/draft`),
  scout: (playerId: number) => post<ProspectRow>(`/players/${playerId}/scout`),
  draftPick: (leagueId: number, playerId: number) =>
    post<DraftResult>(`/leagues/${leagueId}/draft/pick`, { player_id: playerId }),
  playDraft: (seasonId: number, until: DraftUntil) =>
    post<DraftResult>(`/seasons/${seasonId}/draft`, { until }),
  cutDown: (teamId: number) => post<PlayerSummary[]>(`/teams/${teamId}/cut-down`),
  tradeCenter: (leagueId: number, partnerId?: number) =>
    request<TradeCenter>(`/leagues/${leagueId}/trades${partnerId ? `?partner_id=${partnerId}` : ""}`),
  evaluateTrade: (leagueId: number, proposal: TradeProposal) =>
    post<TradeEvaluation>(`/leagues/${leagueId}/trades/evaluate`, proposal),
  proposeTrade: (leagueId: number, proposal: TradeProposal) =>
    post<TradeResult>(`/leagues/${leagueId}/trades`, proposal),
  makeTradeOffer: (leagueId: number, proposal: TradeProposal, note?: string) =>
    post<TradeOffer>(`/leagues/${leagueId}/trade-offers`, { proposal, note: note || null }),
  acceptOffer: (offerId: number) => post<TradeOffer>(`/trade-offers/${offerId}/accept`),
  rejectOffer: (offerId: number) => post<TradeOffer>(`/trade-offers/${offerId}/reject`),
  withdrawTradeOffer: (offerId: number) => post<TradeOffer>(`/trade-offers/${offerId}/withdraw`),
  counterOffer: (offerId: number, proposal: TradeProposal, note?: string) =>
    post<TradeOffer>(`/trade-offers/${offerId}/counter`, { proposal, note: note || null }),
  vetoOffer: (offerId: number, reason?: string) =>
    post<TradeOffer>(`/trade-offers/${offerId}/veto`, { reason: reason || null }),
  approveOffer: (offerId: number) => post<TradeOffer>(`/trade-offers/${offerId}/approve`),
  history: (leagueId: number) => request<HistoryOut>(`/leagues/${leagueId}/history`),
  career: (playerId: number) => request<CareerOut>(`/players/${playerId}/career`),
  playback: (gameId: number) => request<GamePlayback>(`/games/${gameId}/playback`),
  playbook: () => request<Playbook>("/playbook"),
  gamePlan: (teamId: number) => request<GamePlan>(`/teams/${teamId}/game-plan`),
  saveGamePlan: (teamId: number, plan: GamePlanInput) =>
    request<GamePlan>(`/teams/${teamId}/game-plan`, { method: "PUT", body: JSON.stringify(plan) }),
  resetGamePlan: (teamId: number) =>
    request<GamePlan>(`/teams/${teamId}/game-plan`, { method: "DELETE" }),
  nextGame: () => request<NextGame>("/franchise/next-game"),
  coachState: (gameId: number) => request<CoachState>(`/games/${gameId}/coach`),
  startCoaching: (gameId: number) => post<CoachState>(`/games/${gameId}/coach`),
  coachCall: (gameId: number, call: CoachCallIn) => post<CoachState>(`/games/${gameId}/coach/call`, call),
  coachAuto: (gameId: number, scope: "play" | "drive" | "game") =>
    post<CoachState>(`/games/${gameId}/coach/auto`, { scope }),
  advance: (seasonId: number) => post<Season>(`/seasons/${seasonId}/advance`),
  startJob: (leagueId: number, kind: JobKind, seasons?: number) =>
    post<Job>(`/leagues/${leagueId}/jobs`, seasons ? { kind, seasons } : { kind }),
  dynastyReport: (leagueId: number, fromYear: number, toYear: number) =>
    request<DynastyReport>(`/leagues/${leagueId}/dynasty?from_year=${fromYear}&to_year=${toYear}`),
  job: (jobId: number) => request<Job>(`/jobs/${jobId}`),
  cancelJob: (jobId: number) => request<Job>(`/jobs/${jobId}`, { method: "DELETE" }),
  playoffs: (leagueId: number) => request<PlayoffsOut>(`/leagues/${leagueId}/playoffs`),
  leaders: (leagueId: number, category?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (limit) params.set("limit", String(limit));
    const query = params.size ? `?${params}` : "";
    return request<LeadersOut>(`/leagues/${leagueId}/leaders${query}`);
  },
  teamStats: (leagueId: number) => request<TeamSeasonRow[]>(`/leagues/${leagueId}/team-stats`),
  playerStats: (playerId: number) => request<PlayerSeasonStats>(`/players/${playerId}/stats`),
  previewImport: (teamId: number, file: File, mode: ImportMode) =>
    request<ImportPreview>(`/teams/${teamId}/roster-import/preview`, {
      method: "POST",
      body: importForm(file, mode),
    }),
  commitImport: (teamId: number, file: File, mode: ImportMode, skipInvalid: boolean) =>
    request<ImportResult>(`/teams/${teamId}/roster-import/commit`, {
      method: "POST",
      body: importForm(file, mode, skipInvalid),
    }),
};

function importForm(file: File, mode: ImportMode, skipInvalid?: boolean): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);
  if (skipInvalid !== undefined) form.append("skip_invalid", String(skipInvalid));
  return form;
}

export function rosterExportUrl(teamId: number, format: ImportFormat): string {
  return `${apiBaseUrl()}/api/teams/${teamId}/roster-export.${format}`;
}

export function importTemplateUrl(format: ImportFormat): string {
  return `${apiBaseUrl()}/api/roster-import/template.${format}`;
}

export type Result<T> = { ok: true; data: T } | { ok: false; error: unknown };

/** Await a loader and capture failure as a value, so pages can render an error state. */
export async function attempt<T>(load: () => Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, data: await load() };
  } catch (error) {
    // Signed out (or the session expired): off to sign in, then back here.
    if (error instanceof ApiError && error.status === 401) redirect("/signin");
    return { ok: false, error };
  }
}
