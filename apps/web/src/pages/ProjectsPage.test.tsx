import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProjectsPage from "./ProjectsPage";

const scriptProvider = {
  id: 1,
  name: "剧本模型",
  base_url: "https://llm.example.com/v1",
  model: "script-pro",
  api_key_env: "SCRIPT_API_KEY",
  capabilities: ["script"],
  enabled: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const imageProvider = {
  ...scriptProvider,
  id: 2,
  name: "图像模型",
  base_url: "https://image.example.com/v1",
  model: "image-plus",
  api_key_env: "IMAGE_API_KEY",
  capabilities: ["image"],
};
const videoProvider = {
  ...scriptProvider,
  id: 3,
  name: "视频模型",
  base_url: "https://video.example.com/v1",
  model: "video-max",
  api_key_env: "VIDEO_API_KEY",
  capabilities: ["video"],
};
const project = {
  id: 7,
  title: "旧港",
  source_filename: "harbor.txt",
  source_media_type: "text/plain",
  provider_id: 1,
  provider_routes: [
    { role: "script", provider_id: 1 },
    { role: "image", provider_id: 2 },
    { role: "video", provider_id: 3 },
  ],
  created_at: "2026-01-01T00:00:00Z",
  stages: [],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi() {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/healthz") {
      return Promise.resolve(jsonResponse({ status: "ok", database: "ok" }));
    }
    if (url === "/api/v1/llm-providers/" && init?.method === "POST") {
      return Promise.resolve(
        jsonResponse({
          ...videoProvider,
          id: 4,
          name: "新视频模型",
        }),
      );
    }
    if (url === "/api/v1/llm-providers/") {
      return Promise.resolve(jsonResponse([scriptProvider, imageProvider, videoProvider]));
    }
    if (url === "/api/v1/projects" && init?.method === "POST") {
      expect(init.body).toBeInstanceOf(FormData);
      expect((init.body as FormData).get("provider_id")).toBe("1");
      expect((init.body as FormData).get("image_provider_id")).toBe("2");
      expect((init.body as FormData).get("video_provider_id")).toBe("3");
      expect((init.body as FormData).get("file")).toBeInstanceOf(File);
      return Promise.resolve(jsonResponse(project));
    }
    if (url === "/api/v1/projects") {
      return Promise.resolve(jsonResponse([project]));
    }
    return Promise.reject(new Error(`Unexpected ${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProjectsPage", () => {
  it("creates capability providers and uploads three model routes", async () => {
    const fetchMock = mockApi();
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("旧港")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Provider 名称"), {
      target: { value: "新视频模型" },
    });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "https://video.example.com/v2" },
    });
    fireEvent.change(screen.getByLabelText("模型名称"), {
      target: { value: "video-max-v2" },
    });
    fireEvent.change(screen.getByLabelText("密钥环境变量"), {
      target: { value: "VIDEO_API_KEY" },
    });
    fireEvent.click(screen.getByLabelText("剧本生成"));
    fireEvent.click(screen.getByLabelText("文生图"));
    fireEvent.click(screen.getByLabelText("视频生成"));
    fireEvent.click(screen.getByRole("button", { name: "添加 Provider" }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([url, init]) => url === "/api/v1/llm-providers/" && init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      const body = JSON.parse(createCall![1]!.body as string);
      expect(body.base_url).toBe("https://video.example.com/v2");
      expect(body.capabilities).toEqual(["image", "video"]);
    });

    const file = new File(["第一章 归来\n林夏回到旧港。"], "harbor.txt", {
      type: "text/plain",
    });
    fireEvent.change(screen.getByLabelText("小说文件"), {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByLabelText("剧本模型"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("文生图模型"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("视频模型"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/projects",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
