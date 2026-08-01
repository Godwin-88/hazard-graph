import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '@/lib/api';

const API_BASE = '/api/v1';

async function fetchAlerts(status?: string) {
  const params = status ? `?status=${status}` : '';
  return fetchJson(`${API_BASE}/alerts${params}`);
}

async function approveAlert(id: string, messageText: string) {
  return fetchJson(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ action: 'approve', message_text: messageText }),
  });
}

async function rejectAlert(id: string, reason: string) {
  return fetchJson(`${API_BASE}/alerts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ action: 'reject', reason }),
  });
}

async function dispatchAlert(id: string) {
  return fetchJson(`${API_BASE}/alerts/${id}/dispatch`, {
    method: 'POST',
  });
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
    mutationFn: ({ id, messageText }: { id: string; messageText: string }) =>
      approveAlert(id, messageText),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useRejectAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      rejectAlert(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export function useDispatchAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => dispatchAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] });
    },
  });
}

export interface Alert {
  id: string;
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