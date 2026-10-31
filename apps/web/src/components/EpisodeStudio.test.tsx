import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  fetchVideoProviders: vi.fn(),
  fetchRenderProgress: vi.fn(),
  fetchEpisodeExport: vi.fn(),
  startEpisodeRender: vi.fn(),
  retryRenderCut: vi.fn(),
}));

vi.mock("../api", () => api);

import EpisodeStudio from "./EpisodeStudio";

const storyboard = {
  episodes: [{
    episode: 1,
    segments: [{
      index: 1,
      duration_s: 7,
      cuts: [],
    }],
  }],
};

const failedRender = {
  project_id: 7,
  episode: 1,
  status: "failed",
  completed_cuts: 1,
  total_cuts: 2,
  segments: [{
    index: 1,
    status: "failed",
    completed_cuts: 1,
    total_cuts: 2,
    cuts: [
      { index: 1, status: "done", attempt_count: 1, provider_id: null, clip_path: "clip-1.mp4", error: null },
      { index: 2, status: "failed", attempt_count: 2, provider_id: null, clip_path: null, error: "生成失败" },
    ],
  }],
};

const exported = {
  episode: 1,
  status: "done",
  burned_path: "exports/episode_1.mp4",
  clean_path: "exports/episode_1_clean.mp4",
  srt_path: "exports/episode_1.srt",
  vtt_path: "exports/episode_1.vtt",
};

describe("EpisodeStudio", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.fetchVideoProviders.mockResolvedValue([
      { id: 1, name: "动作模型", kind: "seedance", model: "seedance-pro", config_json: {} },
      { id: 2, name: "文戏模型", kind: "minimax_h3", model: "MiniMax-H3", config_json: {} },
    ]);
    api.fetchRenderProgress.mockResolvedValue(failedRender);
    api.fetchEpisodeExport.mockResolvedValue(exported);
    api.startEpisodeRender.mockResolvedValue({ status: "pending" });
    api.retryRenderCut.mockResolvedValue({ status: "pending" });
  });

  it("selects backends, retries a cut, and plays switchable subtitles", async () => {
    render(<EpisodeStudio projectId={7} storyboard={storyboard} />);

    expect(await screen.findByText(/生成失败/)).toBeInTheDocument();
    const video = await screen.findByTestId("episode-player");
    expect(video).toHaveAttribute("src", "/api/v1/assets/exports/episode_1_clean.mp4");
    const track = screen.getByTestId("episode-subtitles");
    expect(track).toHaveAttribute("mode", "showing");
    fireEvent.click(screen.getByRole("button", { name: "隐藏字幕" }));
    expect(track).toHaveAttribute("mode", "hidden");
    expect(screen.getByRole("link", { name: "下载烧录版" })).toHaveAttribute(
      "href",
      "/api/v1/assets/exports/episode_1.mp4",
    );
    expect(screen.getByRole("link", { name: "下载 SRT" })).toHaveAttribute(
      "href",
      "/api/v1/assets/exports/episode_1.srt",
    );

    fireEvent.change(screen.getByLabelText("默认视频后端"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "开始渲染" }));
    expect(api.startEpisodeRender).toHaveBeenCalledWith(7, 1, {
      video_provider_id: 2,
      segment_providers: {},
    });
    fireEvent.click(screen.getByRole("button", { name: "重试该镜" }));
    expect(api.retryRenderCut).toHaveBeenCalledWith(7, 1, 1, 2);
  });

  it("keeps polling while the first render asset does not exist yet", async () => {
    api.fetchRenderProgress
      .mockRejectedValueOnce(new Error("not found"))
      .mockRejectedValueOnce(new Error("not found"))
      .mockResolvedValue(failedRender);
    render(<EpisodeStudio projectId={7} storyboard={storyboard} />);
    await act(async () => {
      await Promise.resolve();
    });
    fireEvent.click(screen.getByRole("button", { name: "开始渲染" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2100));
    });

    expect(api.fetchRenderProgress).toHaveBeenCalledTimes(3);
  });
});
