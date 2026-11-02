export const API_BASE = '/api/v1';
const BASE = API_BASE;
const TOKEN_KEY = 'cc_access_token';

let accessToken: string | null = localStorage.getItem(TOKEN_KEY);

/** Access-JWT в памяти браузера (S-08: лёгкий dev-логин). */
export function setToken(token: string | null): void {
  accessToken = token;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function getToken(): string | null {
  return accessToken;
}

/** Контракт ошибок — RFC 7807 (Design §12.1): code/detail/status. */
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/**
 * Общий REST-запрос к API v1. JSON — camelCase (Design §12.1),
 * cookies включаем (refresh — HttpOnly cookie, S-02), Bearer — access-JWT.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (accessToken && !headers.Authorization) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      credentials: 'include',
      headers,
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Сеть недоступна: API не отвечает');
  }

  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as ProblemDetails | null;
    throw new ApiError(
      response.status,
      problem?.code ?? 'unknown_error',
      problem?.detail ?? problem?.title ?? `HTTP ${response.status}`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// --- DTO (заморозка контрактов — docs/SPEC.md)

export interface HealthDto {
  status: string;
  db: boolean;
  redis: boolean;
}

export const fetchHealth = (): Promise<HealthDto> => apiFetch<HealthDto>('/healthz');

export interface AuthOut {
  accessToken: string;
  tokenType: string;
  user: {
    id: string;
    email: string;
    role: string;
    emailVerified: boolean;
  };
}

export async function login(email: string, password: string): Promise<AuthOut> {
  const data = await apiFetch<AuthOut>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  setToken(data.accessToken);
  return data;
}

export function logout(): void {
  setToken(null);
}

// --- python_teacher (S-08)

export interface AssignmentDto {
  id: string;
  slug: string;
  title: string;
  level: 'novice' | 'intermediate' | 'advanced';
  topic: string;
  testsCount: number;
}

export interface AssignmentDetailDto extends AssignmentDto {
  statement: string;
  starterCode: string;
  tests: string[] | null;
}

export interface SubmissionDto {
  id: string;
  assignmentId: string;
  verdict: 'passed' | 'failed' | 'timeout' | 'restricted' | 'error';
  passedTests: number;
  totalTests: number;
  failedTest: number | null;
  stdoutDigest: string | null;
  durationMs: number | null;
  createdAt: string;
}

export function fetchAssignments(): Promise<{ items: AssignmentDto[]; total: number }> {
  return apiFetch('/py/assignments?pageSize=100');
}

export function fetchAssignmentDetail(id: string): Promise<AssignmentDetailDto> {
  return apiFetch(`/py/assignments/${id}`);
}

export function submitSolution(id: string, code: string): Promise<SubmissionDto> {
  return apiFetch(`/py/assignments/${id}/submit`, {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

// --- chess_lab (S-11)

export interface EngineLineDto {
  multipv: number;
  depth: number;
  scoreCp: number | null;
  mate: number | null;
  moveUci: string;
  pv: string[];
}

export interface InsightOut {
  fen: string;
  level: string;
  facts: EngineLineDto[];
  factsText: string[];
  explanation: string;
  modelUsed: string;
  knowledge: string[];
}

export function insightPosition(fen: string, level?: string): Promise<InsightOut> {
  return apiFetch('/chess/insight', {
    method: 'POST',
    body: JSON.stringify({ fen, level: level || null }),
  });
}

export function fetchPositions(): Promise<{
  items: { id: string; fen: string; meta: Record<string, unknown> }[];
  total: number;
}> {
  return apiFetch('/chess/positions?limit=20');
}

// --- chess_lab: PGN-анализ (S-12/S-33)

export interface GameUploadOut {
  gameId: string;
  status: string;
}

export interface GameStatusOut {
  gameId: string;
  status: string;
  blunderCount: number;
  summary: Record<string, unknown>;
}

export interface BlunderDto {
  ply: number;
  fenBefore: string;
  playedSan: string;
  playedUci: string;
  bestSan: string;
  bestUci: string;
  deltaCp: number;
  classification: string;
  explanation: string | null;
}

export interface BlundersOut {
  gameId: string;
  status: string;
  blunders: BlunderDto[];
  summary: Record<string, unknown>;
}

export interface BlunderExplainOut {
  ply: number;
  explanation: string;
  modelUsed: string;
  knowledge: string[];
}

export function uploadGame(pgn: string): Promise<GameUploadOut> {
  return apiFetch('/chess/games/upload', {
    method: 'POST',
    body: JSON.stringify({ pgn }),
  });
}

export function fetchGameStatus(gameId: string): Promise<GameStatusOut> {
  return apiFetch(`/chess/games/${gameId}`);
}

export function fetchBlunders(gameId: string): Promise<BlundersOut> {
  return apiFetch(`/chess/games/${gameId}/blunders`);
}

export function explainBlunder(
  gameId: string,
  ply: number,
): Promise<BlunderExplainOut> {
  return apiFetch(`/chess/games/${gameId}/blunders/explain`, {
    method: 'POST',
    body: JSON.stringify({ ply }),
  });
}

// --- classes (S-40)

export interface ClassDto {
  id: string;
  name: string;
  teacherId: string;
  inviteCode: string | null;
  memberCount: number;
  createdAt: string;
}

export interface ClassMemberDto {
  userId: string;
  email: string;
  displayName: string | null;
  level: string;
  joinedAt: string;
}

export interface ClassDetailDto extends ClassDto {
  members: ClassMemberDto[];
}

export interface ClassSkillDto {
  slug: string;
  titleRu: string;
  domain: string;
  score: number;
  week: string | null;
}

export interface ClassDashboardMemberDto {
  userId: string;
  email: string;
  displayName: string | null;
  level: string;
  joinedAt: string;
  skills: ClassSkillDto[];
  flagsCount: number;
  newFlagsCount: number;
  matchesCount: number;
  wins: number;
  losses: number;
  draws: number;
  elo: number;
}

export interface ClassDashboardDto {
  classId: string;
  className: string;
  memberCount: number;
  members: ClassDashboardMemberDto[];
}

export function fetchClasses(): Promise<ClassDto[]> {
  return apiFetch('/classes');
}

export function createClass(name: string): Promise<ClassDto> {
  return apiFetch('/classes', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function joinClass(inviteCode: string): Promise<ClassDto> {
  return apiFetch('/classes/join', {
    method: 'POST',
    body: JSON.stringify({ inviteCode }),
  });
}

export function fetchClassDetail(classId: string): Promise<ClassDetailDto> {
  return apiFetch(`/classes/${classId}`);
}

export function fetchClassDashboard(
  classId: string,
): Promise<ClassDashboardDto> {
  return apiFetch(`/classes/${classId}/dashboard`);
}

export function rotateClassInvite(classId: string): Promise<ClassDto> {
  return apiFetch(`/classes/${classId}/invite`, { method: 'POST' });
}

export function addClassMember(
  classId: string,
  email: string,
): Promise<ClassMemberDto> {
  return apiFetch(`/classes/${classId}/members`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export function removeClassMember(
  classId: string,
  userId: string,
): Promise<void> {
  return apiFetch(`/classes/${classId}/members/${userId}`, {
    method: 'DELETE',
  });
}

// --- profile / progress (S-42)

export interface ProfileDto {
  id: string;
  email: string;
  role: string;
  displayName: string | null;
  level: string | null;
  billingTier: string | null;
  ageGroup: 'child' | 'teen' | 'adult' | 'unknown';
  emailVerified: boolean;
  isActive: boolean;
  prefs: Record<string, unknown>;
  createdAt: string;
}

export interface AchievementDto {
  code: string;
  titleRu: string;
  description: string;
  icon: string;
  awarded: boolean;
  awardedAt: string | null;
}

export interface ProgressDto {
  userId: string;
  solvedCount: number;
  topics: Record<string, number>;
  currentStreak: number;
  longestStreak: number;
  lastSolvedOn: string | null;
  achievements: AchievementDto[];
}

export function fetchMyProfile(): Promise<ProfileDto> {
  return apiFetch('/profile/me');
}

export function updateMyProfile(payload: {
  displayName?: string;
  ageGroup?: string;
}): Promise<ProfileDto> {
  return apiFetch('/profile/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function fetchMyProgress(): Promise<ProgressDto> {
  return apiFetch('/progress/me');
}

// --- voice (S-44)

export interface VoiceStatusDto {
  configured: boolean;
  provider: string;
  modelId: string;
  voiceId: string;
}

export function fetchVoiceStatus(): Promise<VoiceStatusDto> {
  return apiFetch('/voice/status');
}

/** POST /voice/speak → audio/mpeg (Blob); 503 = озвучка не настроена. */
export async function speakText(text: string): Promise<Blob> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const response = await fetch(`${BASE}/voice/speak`, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as ProblemDetails | null;
    throw new ApiError(
      response.status,
      problem?.code ?? 'voice_error',
      problem?.detail ?? 'Озвучка недоступна',
    );
  }
  return response.blob();
}

// --- tournaments / export (S-45)

export interface TournamentDto {
  id: string;
  name: string;
  format: string;
  status: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  meta: Record<string, unknown>;
}

export interface TournamentParticipantDto {
  botVersionId: string;
  userId: string;
  email: string | null;
  displayName: string | null;
  seed: number;
  wins: number;
  losses: number;
  draws: number;
  points: number;
  rank: number | null;
}

export interface TournamentMatchDto {
  roundNo: number;
  matchNo: number;
  botAId: string;
  botBId: string;
  winnerId: string | null;
  result: string;
  movesCount: number;
  durationMs: number;
}

export interface TournamentDetailDto extends TournamentDto {
  participants: TournamentParticipantDto[];
  matches: TournamentMatchDto[];
}

export function fetchTournaments(): Promise<TournamentDto[]> {
  return apiFetch('/tournaments');
}

export function fetchTournament(id: string): Promise<TournamentDetailDto> {
  return apiFetch(`/tournaments/${id}`);
}

export function createTournament(payload: {
  name: string;
  format: string;
  botVersionIds: number[];
}): Promise<TournamentDetailDto> {
  return apiFetch('/admin/tournaments', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Скачать защищённый экспорт (CSV/JSON) через Bearer. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const response = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers,
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as ProblemDetails | null;
    throw new ApiError(
      response.status,
      problem?.code ?? 'export_error',
      problem?.detail ?? 'Ошибка экспорта',
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
