import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  fetchProject: vi.fn(),
  fetchProviders: vi.fn(),
  fetchProjectStatus: vi.fn(),
  fetchOutline: vi.fn(),
  fetchScript: vi.fn(),
  fetchCharacters: vi.fn(),
  fetchStoryboard: vi.fn(),
  confirmAnchor: vi.fn(),
  regenerateCharacterImage: vi.fn(),
  retryStage: vi.fn(),
}));

vi.mock("../api", () => api);

import ProjectDetailPage from "./ProjectDetailPage";

const outline = {
  synopsis: "林夏揭开旧港真相。",
  cast: [{ name: "林夏", role: "调查记者", weight: 1 }],
  episode_beat: [
    {
      episode: 1,
      summary: "林夏收到录音笔。",
      payoff_type: "身份反转",
      payoff_intensity: 5,
    },
  ],
  asset_list: ["录音笔"],
};

const script = {
  cast: outline.cast,
  episodes: [
    {
      episode: 1,
      estimated_duration_s: 6,
      scenes: [
        {
          index: 1,
          heading: "旧港仓库·夜·内景",
          action_beats: [
            { order: 1, text: "林夏按下录音笔。" },
            { order: 3, text: "周衡停在门口。" },
          ],
          lines: [
            {
              order: 2,
              character: "林夏",
              emotion: "震惊",
              text: "你在说谎。",
            },
            {
              order: 4,
              character: "林夏",
              emotion: "坚定",
              text: "我承认。",
            },
          ],
        },
      ],
    },
  ],
};

function status(outlineStatus: string, scriptStatus: string, error: string | null = null) {
  return {
    project_id: 7,
    stages: [
      {
        stage: "upload",
        status: "done",
        completed_items: 1,
        total_items: 1,
        attempt_count: 1,
        requires_attention: false,
        error: null,
      },
      {
        stage: "outline",
        status: outlineStatus,
        completed_items: outlineStatus === "done" ? 1 : 0,
        total_items: 1,
        attempt_count: 1,
        requires_attention: false,
        error: null,
      },
      {
        stage: "script",
        status: scriptStatus,
        completed_items: scriptStatus === "done" ? 1 : 0,
        total_items: 1,
        attempt_count: 1,
        requires_attention: scriptStatus === "failed",
        error,
      },
    ],
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/projects/7"]}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  api.fetchProject.mockResolvedValue({
    id: 7,
    title: "旧港",
    provider_id: 1,
    provider_routes: [
      { role: "script", provider_id: 1 },
      { role: "image", provider_id: 2 },
      { role: "video", provider_id: 3 },
    ],
  });
  api.fetchProviders.mockResolvedValue([
    { id: 1, name: "剧本专用", model: "script-pro", capabilities: ["script"] },
    { id: 2, name: "图像专用", model: "image-plus", capabilities: ["image"] },
    { id: 3, name: "视频专用", model: "video-max", capabilities: ["video"] },
  ]);
  api.fetchOutline.mockResolvedValue(outline);
  api.fetchScript.mockResolvedValue(script);
  api.fetchCharacters.mockResolvedValue({ characters: [] });
  api.fetchStoryboard.mockResolvedValue({ episodes: [] });
  api.confirmAnchor.mockResolvedValue({ status: "queued" });
  api.regenerateCharacterImage.mockResolvedValue({ status: "queued" });
  api.retryStage.mockResolvedValue({ project_id: 7, stage: "script", status: "pending" });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ProjectDetailPage", () => {
  it("polls every two seconds until done and renders both assets", async () => {
    vi.useFakeTimers();
    api.fetchProjectStatus
      .mockResolvedValueOnce(status("running", "pending"))
      .mockResolvedValueOnce(status("done", "done"));

    renderPage();

    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("大纲生成中")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await Promise.resolve();
    });

    expect(screen.getAllByText("林夏").length).toBeGreaterThan(0);
    expect(screen.getByText(/身份反转/)).toBeInTheDocument();
    expect(screen.getByText("林夏按下录音笔。")).toBeInTheDocument();
    expect(screen.getByText("你在说谎。")).toBeInTheDocument();
    expect(screen.getByText("6 秒")).toBeInTheDocument();
    expect(screen.getByText("模型协作")).toBeInTheDocument();
    expect(screen.getByText(/剧本专用/)).toBeInTheDocument();
    expect(screen.getByText(/图像专用/)).toBeInTheDocument();
    expect(screen.getByText(/视频专用/)).toBeInTheDocument();
    expect(api.fetchProjectStatus).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(api.fetchProjectStatus).toHaveBeenCalledTimes(2);
  });

  it("shows failure and retries the failed stage", async () => {
    api.fetchProjectStatus
      .mockResolvedValueOnce(status("done", "failed", "生成失败"))
      .mockResolvedValueOnce(status("done", "done"));

    renderPage();

    expect(await screen.findByText("生成失败")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试该阶段" }));

    expect(api.retryStage).toHaveBeenCalledWith(7, "script");
    expect(await screen.findByText("你在说谎。")).toBeInTheDocument();
  });

  it("stops polling a failed upstream stage", async () => {
    vi.useFakeTimers();
    api.fetchProjectStatus.mockResolvedValue(status("failed", "pending", "大纲失败"));

    renderPage();
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getAllByText("大纲失败").length).toBeGreaterThan(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(api.fetchProjectStatus).toHaveBeenCalledTimes(1);
  });

  it("continues polling after a transient request failure", async () => {
    vi.useFakeTimers();
    api.fetchProjectStatus
      .mockRejectedValueOnce(new Error("网络错误"))
      .mockResolvedValueOnce(status("done", "done"));

    renderPage();
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("网络错误")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await Promise.resolve();
    });
    expect(screen.getByText("你在说谎。")).toBeInTheDocument();
    expect(api.fetchProjectStatus).toHaveBeenCalledTimes(2);
  });

  it("falls back to the legacy script provider without route or capability fields", async () => {
    api.fetchProject.mockResolvedValue({
      id: 7,
      title: "旧项目",
      provider_id: 1,
      provider_routes: [],
    });
    api.fetchProviders.mockResolvedValue([
      { id: 1, name: "旧剧本模型", model: "legacy-script" },
    ]);
    api.fetchProjectStatus.mockResolvedValue(status("done", "done"));

    renderPage();

    expect(await screen.findByText(/旧剧本模型/)).toBeInTheDocument();
    expect(screen.getByText(/legacy-script/)).toBeInTheDocument();
  });

  it("loads failed character assets and keeps polling after an image retry", async () => {
    vi.useFakeTimers();
    const stage3Status = (characterStatus: string, storyboardStatus: string) => ({
      project_id: 7,
      stages: [
        ...status("done", "done").stages,
        {
          stage: "characters",
          status: characterStatus,
          completed_items: 0,
          total_items: 1,
          attempt_count: 1,
          requires_attention: characterStatus === "failed",
          error: characterStatus === "failed" ? "图片失败" : null,
        },
        {
          stage: "storyboard",
          status: storyboardStatus,
          completed_items: 0,
          total_items: 1,
          attempt_count: 0,
          requires_attention: false,
          error: null,
        },
      ],
    });
    api.fetchProjectStatus
      .mockResolvedValueOnce(stage3Status("failed", "pending"))
      .mockResolvedValueOnce(stage3Status("running", "pending"))
      .mockResolvedValueOnce(stage3Status("done", "done"));
    api.fetchCharacters.mockResolvedValue({
      characters: [{
        id: 1,
        name: "林夏",
        biography: "调查记者",
        prompt_zh: "林夏",
        prompt_en: "Lin Xia",
        voice_prompt: "冷静女声",
        anchor_features: ["红绳"],
        anchor_confirmed: true,
        images: [{
          id: 2,
          label: "avatar",
          status: "failed",
          path: null,
          width: null,
          height: null,
          format: null,
          workflow_id: null,
          error: "图片失败",
        }],
      }],
    });

    renderPage();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.regenerateCharacterImage).toHaveBeenCalledWith(7, 2);
    expect(api.fetchProjectStatus).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await Promise.resolve();
    });
    expect(api.fetchProjectStatus).toHaveBeenCalledTimes(3);
    expect(api.fetchCharacters).toHaveBeenCalled();
  });
});
