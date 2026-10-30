import type {
  HealthResponse,
  LLMProvider,
  Outline,
  ProjectDetail,
  ProjectStatus,
  ProjectSummary,
  Script,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(body?.detail || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/healthz");
}

export function fetchProviders(): Promise<LLMProvider[]> {
  return request<LLMProvider[]>("/api/v1/llm-providers/");
}

export function fetchProjects(): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>("/projects");
}

export function fetchProject(id: number): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/projects/${id}`);
}

export function fetchProjectStatus(id: number): Promise<ProjectStatus> {
  return request<ProjectStatus>(`/projects/${id}/status`);
}

export function fetchOutline(id: number): Promise<Outline> {
  return request<Outline>(`/projects/${id}/outline`);
}

export function fetchScript(id: number): Promise<Script> {
  return request<Script>(`/projects/${id}/script`);
}

export function uploadProject(file: File, providerId: number): Promise<ProjectDetail> {
  const body = new FormData();
  body.append("provider_id", String(providerId));
  body.append("file", file);
  return request<ProjectDetail>("/projects", { method: "POST", body });
}

export function retryStage(
  id: number,
  stage: "outline" | "script",
): Promise<{ project_id: number; stage: string; status: string }> {
  return request(`/projects/${id}/stages/${stage}/retry`, { method: "POST" });
}
