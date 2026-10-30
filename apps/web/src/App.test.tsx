import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const provider = {
  id: 1,
  name: "primary",
  base_url: "https://api.example.com/v1",
  model: "example-model",
  api_key_env: "OPENAI_API_KEY",
  enabled: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi({
  health = jsonResponse({ status: "ok", database: "ok" }),
  providers = jsonResponse([provider]),
}: {
  health?: Response;
  providers?: Response;
} = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/healthz") {
        return Promise.resolve(health);
      }
      if (url === "/api/v1/llm-providers/") {
        return Promise.resolve(providers);
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders health and provider data", async () => {
    mockApi();
    render(<App />);

    expect(screen.getByText("正在检查服务状态…")).toBeInTheDocument();
    expect(screen.getByText("正在加载 Provider…")).toBeInTheDocument();
    expect(await screen.findByText("服务正常")).toBeInTheDocument();
    expect(screen.getByText("数据库连接正常")).toBeInTheDocument();
    expect(await screen.findByText("primary")).toBeInTheDocument();
    expect(screen.getByText("https://api.example.com/v1")).toBeInTheDocument();
    expect(screen.getByText("example-model")).toBeInTheDocument();
    expect(screen.getByText("OPENAI_API_KEY")).toBeInTheDocument();
    expect(screen.getByText("已启用")).toBeInTheDocument();
  });

  it("renders an empty provider state", async () => {
    mockApi({ providers: jsonResponse([]) });
    render(<App />);

    expect(await screen.findByText("暂未配置 Provider")).toBeInTheDocument();
  });

  it("keeps providers visible when health fails", async () => {
    mockApi({ health: jsonResponse({ detail: "down" }, 503) });
    render(<App />);

    expect(await screen.findByText(/健康检查失败/)).toBeInTheDocument();
    expect(await screen.findByText("primary")).toBeInTheDocument();
  });

  it("keeps health visible when providers fail", async () => {
    mockApi({ providers: jsonResponse({ detail: "down" }, 500) });
    render(<App />);

    expect(await screen.findByText(/Provider 加载失败/)).toBeInTheDocument();
    expect(await screen.findByText("服务正常")).toBeInTheDocument();
  });
});
