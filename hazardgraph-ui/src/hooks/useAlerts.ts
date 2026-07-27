import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = 'http://localhost:8000/api/v1';

async function fetchAlerts(status?: string) {
  const token = sessionStorage.getItem('access_token');
  const params = status ? `?status=${status}` : '';
  const res = await fetch(`${API_BASE}/alerts${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Failed to fetch alerts');
  return res.json();
}

async function approveAlert(id: number, messageText: string) {
  const token = sessionStorage.getItem('access_token');
  const res = await fetch(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ action: 'approve', message_text: messageText }),
  });
  if (!res.ok) throw new Error('Failed to approve alert');
  return res.json();
}

async function rejectAlert(id: number, reason: string) {
  const token = sessionStorage.getItem('access_token');
  const res = await fetch(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ action: 'reject', reason }),
  });
  if (!res.ok) throw new Error('Failed to reject alert');
  return res.json();
}

async function dispatchAlert(id: number) {
  const token = sessionStorage.getItem('access_token');
  const res = await fetch(`${API_BASE}/alerts/${id}/dispatch`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
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