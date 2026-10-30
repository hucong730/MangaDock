export interface HealthResponse {
  status: string;
  database: string;
}

export interface LLMProvider {
  id: number;
  name: string;
  base_url: string;
  model: string;
  api_key_env: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}
