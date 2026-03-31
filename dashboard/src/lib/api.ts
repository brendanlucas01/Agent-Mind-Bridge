import useSWR from 'swr';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const fetcher = (url: string) => fetch(`${API_BASE}${url}`).then((res) => {
  if (!res.ok) throw new Error('Error fetching data');
  return res.json();
});

export function useHealth() {
  return useSWR('/api/health', fetcher, { refreshInterval: 10000 });
}

export function useProjects() {
  return useSWR('/api/projects', fetcher, { refreshInterval: 5000 });
}

export function useProject(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}` : null, fetcher, { refreshInterval: 5000 });
}

export function useAgents() {
  return useSWR('/api/agents', fetcher, { refreshInterval: 2000 }); 
}

export function useSprint(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}/sprint` : null, fetcher, { refreshInterval: 5000 });
}

export function useSprintsList(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}/sprints` : null, fetcher, { refreshInterval: 10000 });
}

export function useThreads(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}/threads` : null, fetcher, { refreshInterval: 10000 });
}

export function useActivity(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}/activity` : null, fetcher, { refreshInterval: 5000 });
}

export function useTasks(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}/tasks` : null, fetcher, { refreshInterval: 5000 });
}

export function useHandoffs(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}/handoffs` : null, fetcher, { refreshInterval: 10000 });
}

export function useSkills(projectId: string | null) {
  return useSWR(projectId ? `/api/projects/${projectId}/skills` : null, fetcher, { refreshInterval: 30000 });
}

export function useThreadEntries(threadId: string | null) {
  return useSWR(threadId ? `/api/threads/${threadId}/entries` : null, fetcher, { refreshInterval: 5000 });
}
