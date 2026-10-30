import type { HealthResponse, LLMProvider } from "./types";

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/healthz");
}

export function fetchProviders(): Promise<LLMProvider[]> {
  return request<LLMProvider[]>("/api/v1/llm-providers/");
}
