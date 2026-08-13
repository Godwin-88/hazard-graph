import { useQuery } from '@tanstack/react-query';

const API_BASE = '/api/v1';

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
  [key: string]: unknown;
}

function getAuthHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('access_token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function fetchGraphNodes() {
  const res = await fetch(`${API_BASE}/graph/nodes`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Failed to fetch graph nodes');
  return res.json();
}

async function fetchGraphEdges() {
  const res = await fetch(`${API_BASE}/graph/edges`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error('Failed to fetch graph edges');
  return res.json();
}

export function useGraphNodes() {
  return useQuery({
    queryKey: ['graph-nodes'],
    queryFn: fetchGraphNodes,
    staleTime: 5 * 60 * 1000,
  });
}

export function useGraphEdges() {
  return useQuery({
    queryKey: ['graph-edges'],
    queryFn: fetchGraphEdges,
    staleTime: 5 * 60 * 1000,
  });
}