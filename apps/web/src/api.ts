import type {
  CreateProviderInput,
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

export function createProvider(input: CreateProviderInput): Promise<LLMProvider> {
  return request<LLMProvider>("/api/v1/llm-providers/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function fetchProjects(): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>("/api/v1/projects");
}

export function fetchProject(id: number): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/v1/projects/${id}`);
}

export function fetchProjectStatus(id: number): Promise<ProjectStatus> {
  return request<ProjectStatus>(`/api/v1/projects/${id}/status`);
}

export function fetchOutline(id: number): Promise<Outline> {
  return request<Outline>(`/api/v1/projects/${id}/outline`);
}

export function fetchScript(id: number): Promise<Script> {
  return request<Script>(`/api/v1/projects/${id}/script`);
}

export function uploadProject(
  file: File,
  providerId: number,
  imageProviderId?: number,
  videoProviderId?: number,
): Promise<ProjectDetail> {
  const body = new FormData();
  body.append("provider_id", String(providerId));
  if (imageProviderId) body.append("image_provider_id", String(imageProviderId));
  if (videoProviderId) body.append("video_provider_id", String(videoProviderId));
  body.append("file", file);
  return request<ProjectDetail>("/api/v1/projects", { method: "POST", body });
}

export function retryStage(
  id: number,
  stage: "outline" | "script",
): Promise<{ project_id: number; stage: string; status: string }> {
  return request(`/api/v1/projects/${id}/stages/${stage}/retry`, { method: "POST" });
}
