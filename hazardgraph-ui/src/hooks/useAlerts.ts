import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = '/api/v1';

async function fetchAlerts(status?: string) {
  const token = sessionStorage.getItem('access_token');
  const params = status ? `?status=${status}` : '';
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  // Use trailing slash to prevent FastAPI 307 redirect which drops auth headers
  const res = await fetch(`${API_BASE}/alerts/${params}`, { headers });
  if (!res.ok) throw new Error('Failed to fetch alerts');
  return res.json();
}

function getAuthHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('access_token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function approveAlert(id: number, messageText: string) {
  const res = await fetch(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'approve', message_text: messageText }),
  });
  if (!res.ok) throw new Error('Failed to approve alert');
  return res.json();
}

async function rejectAlert(id: number, reason: string) {
  const res = await fetch(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
    body: JSON.stringify({ action: 'reject', reason }),
  });
  if (!res.ok) throw new Error('Failed to reject alert');
  return res.json();
}

async function dispatchAlert(id: number) {
  const res = await fetch(`${API_BASE}/alerts/${id}/dispatch`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error('Failed to dispatch alert');
  return res.json();
}

export function useAlerts(status?: string) {
  return useQuery({
    queryKey: ['alerts', status],
    queryFn: () => fetchAlerts(status),
    refetchInterval: 60_000,
  });
}

export function useApproveAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, messageText }: { id: number; messageText: string }) =>
      approveAlert(id, messageText),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useRejectAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      rejectAlert(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useDispatchAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => dispatchAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export interface Alert {
  id: number;
  region_id: string;
  region_name?: string;
  country?: string;
  language: string;
  message_text: string;
  risk_score_at_trigger: number;
  kelly_priority: number;
  confidence?: number;
  status: string;
  generated_at: string;
  approved_at?: string;
  dispatched_at?: string;
  sent_count: number;
  delivered_count: number;
  current_regime?: string;
  components?: Record<string, number>;
}