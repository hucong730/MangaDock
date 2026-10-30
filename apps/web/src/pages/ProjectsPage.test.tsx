import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProjectsPage from "./ProjectsPage";

const provider = {
  id: 1,
  name: "fake",
  base_url: "https://api.example.com/v1",
  model: "fake-model",
  api_key_env: "OPENAI_API_KEY",
  enabled: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const project = {
  id: 7,
  title: "旧港",
  source_filename: "harbor.txt",
  source_media_type: "text/plain",
  provider_id: 1,
  created_at: "2026-01-01T00:00:00Z",
  stages: [],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProjectsPage", () => {
  it("uploads a novel with the selected provider and lists projects", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/healthz") {
        return Promise.resolve(jsonResponse({ status: "ok", database: "ok" }));
      }
      if (url === "/api/v1/llm-providers/") {
        return Promise.resolve(jsonResponse([provider]));
      }
      if (url === "/projects" && init?.method === "POST") {
        expect(init.body).toBeInstanceOf(FormData);
        expect((init.body as FormData).get("provider_id")).toBe("1");
        expect((init.body as FormData).get("file")).toBeInstanceOf(File);
        return Promise.resolve(jsonResponse(project));
      }
      if (url === "/projects") {
        return Promise.resolve(jsonResponse([project]));
      }
      return Promise.reject(new Error(`Unexpected ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("旧港")).toBeInTheDocument();
    expect(screen.getByText("fake")).toBeInTheDocument();
    const file = new File(["第一章 归来\n林夏回到旧港。"], "harbor.txt", {
      type: "text/plain",
    });
    fireEvent.change(screen.getByLabelText("小说文件"), {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByLabelText("模型 Provider"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/projects",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
