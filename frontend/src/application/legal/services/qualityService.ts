import type {
  FeedbackPayload,
  PublishedQuality,
  QualityOverview,
} from '../../../domain/legal/quality';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/** Envía 👍/👎. Devuelve `queued` si el texto autorizado entró a la cola de revisión. */
export async function sendFeedback(payload: FeedbackPayload): Promise<{ ok: boolean; queued: boolean }> {
  try {
    const response = await fetch(`${API_BASE}/feedback`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) return { ok: false, queued: false };
    const data = (await response.json()) as { queued?: boolean };
    return { ok: true, queued: data.queued === true };
  } catch {
    return { ok: false, queued: false };
  }
}

export async function fetchPublishedQuality(signal?: AbortSignal): Promise<PublishedQuality> {
  const response = await fetch(`${API_BASE}/quality/published`, { credentials: 'include', signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = (await response.json()) as { published: PublishedQuality };
  return data.published;
}

export type OverviewResult =
  | { status: 'ok'; overview: QualityOverview }
  | { status: 'forbidden' }
  | { status: 'error' };

export async function fetchQualityOverview(signal?: AbortSignal): Promise<OverviewResult> {
  try {
    const response = await fetch(`${API_BASE}/quality/admin/overview`, { credentials: 'include', signal });
    if (response.status === 401 || response.status === 403) return { status: 'forbidden' };
    if (!response.ok) return { status: 'error' };
    const data = (await response.json()) as { overview: QualityOverview };
    return { status: 'ok', overview: data.overview };
  } catch {
    return { status: 'error' };
  }
}

export async function decideFeedback(id: string, decision: 'accept' | 'reject'): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/feedback/queue/${encodeURIComponent(id)}/decision`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    });
    return response.ok;
  } catch {
    return false;
  }
}
