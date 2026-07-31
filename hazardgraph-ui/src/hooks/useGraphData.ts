import { useQuery } from '@tanstack/react-query';

const API_BASE = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1`;

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  [key: string]: unknown;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
  [key: string]: unknown;
}

async function fetchGraphNodes() {
  const res = await fetch(`${API_BASE}/graph/nodes`);
  if (!res.ok) throw new Error('Failed to fetch graph nodes');
  return res.json();
}

async function fetchGraphEdges() {
  const res = await fetch(`${API_BASE}/graph/edges`);
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