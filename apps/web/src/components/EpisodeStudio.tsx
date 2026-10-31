import { useEffect, useRef, useState } from "react";

import {
  fetchEpisodeExport,
  fetchRenderProgress,
  fetchVideoProviders,
  retryRenderCut,
  startEpisodeRender,
} from "../api";
import type { EpisodeExport, RenderProgress, Storyboard, VideoProvider } from "../types";

interface EpisodeStudioProps {
  projectId: number;
  storyboard: Storyboard;
}

function assetUrl(path: string) {
  return `/api/v1/assets/${path}`;
}

function EpisodeStudio({ projectId, storyboard }: EpisodeStudioProps) {
  const [episode, setEpisode] = useState(storyboard.episodes[0]?.episode ?? 1);
  const [providers, setProviders] = useState<VideoProvider[]>([]);
  const [defaultProvider, setDefaultProvider] = useState("");
  const [segmentProviders, setSegmentProviders] = useState<Record<number, string>>({});
  const [render, setRender] = useState<RenderProgress | null>(null);
  const [exported, setExported] = useState<EpisodeExport | null>(null);
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [starting, setStarting] = useState(false);
  const trackRef = useRef<HTMLTrackElement>(null);

  useEffect(() => {
    let active = true;
    fetchVideoProviders()
      .then((items) => active && setProviders(items))
      .catch(() => active && setProviders([]));
    return () => { active = false; };
  }, [projectId]);

  useEffect(() => {
    let active = true;
    setExported(null);
    fetchRenderProgress(projectId, episode)
      .then((value) => active && setRender(value))
      .catch(() => active && setRender(null));
    fetchEpisodeExport(projectId, episode)
      .then((value) => active && setExported(value))
      .catch(() => active && setExported(null));
    return () => { active = false; };
  }, [projectId, episode, version]);

  useEffect(() => {
    const rendering = render && ["pending", "running"].includes(render.status);
    const composing = render?.status === "done" && !exported;
    if (!starting && !rendering && !composing) return;
    const timer = setTimeout(() => setVersion((value) => value + 1), 2000);
    return () => clearTimeout(timer);
  }, [starting, render, exported, version]);

  useEffect(() => {
    if (render?.status === "failed" || (render?.status === "done" && exported)) {
      setStarting(false);
    }
    const element = trackRef.current;
    if (element) {
      element.setAttribute("mode", showSubtitles ? "showing" : "hidden");
      if (element.track) {
        element.track.mode = showSubtitles ? "showing" : "hidden";
      }
    }
  }, [starting, render, exported, showSubtitles]);

  async function handleStart() {
    setError("");
    try {
      const segment_providers = Object.fromEntries(
        Object.entries(segmentProviders)
          .filter(([, value]) => value)
          .map(([key, value]) => [key, Number(value)]),
      );
      await startEpisodeRender(projectId, episode, {
        ...(defaultProvider ? { video_provider_id: Number(defaultProvider) } : {}),
        segment_providers,
      });
      setRender(null);
      setExported(null);
      setStarting(true);
      setVersion((value) => value + 1);
    } catch (reason) {
      setStarting(false);
      setError(reason instanceof Error ? reason.message : "渲染启动失败");
    }
  }

  async function handleRetry(segment: number, cut: number) {
    setError("");
    try {
      await retryRenderCut(projectId, episode, segment, cut);
      setExported(null);
      setStarting(true);
      setVersion((value) => value + 1);
    } catch (reason) {
      setStarting(false);
      setError(reason instanceof Error ? reason.message : "单镜重试失败");
    }
  }

  return (
    <div className="episode-studio">
      <div className="section-heading">
        <h2>成片</h2>
        <select aria-label="剧集" value={episode} onChange={(event) => setEpisode(Number(event.target.value))}>
          {storyboard.episodes.map((item) => (
            <option key={item.episode} value={item.episode}>第 {item.episode} 集</option>
          ))}
        </select>
      </div>
      {error && <p role="alert" className="error-message">{error}</p>}
      <div className="render-controls">
        <label>默认视频后端
          <select value={defaultProvider} onChange={(event) => setDefaultProvider(event.target.value)}>
            <option value="">Mock / 未配置</option>
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name} · {provider.model}</option>)}
          </select>
        </label>
        <button type="button" onClick={handleStart}>开始渲染</button>
      </div>
      {storyboard.episodes.find((item) => item.episode === episode)?.segments.map((segment) => (
        <label key={segment.index}>第 {segment.index} 段后端
          <select
            value={segmentProviders[segment.index] ?? ""}
            onChange={(event) => setSegmentProviders((current) => ({
              ...current,
              [segment.index]: event.target.value,
            }))}
          >
            <option value="">跟随默认</option>
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
          </select>
        </label>
      ))}
      {render && (
        <div className="render-progress">
          <strong>渲染进度 {render.completed_cuts}/{render.total_cuts} 镜</strong>
          {render.segments.map((segment) => (
            <div key={segment.index} className="render-segment">
              <span>第 {segment.index} 段 · {segment.completed_cuts}/{segment.total_cuts} 镜 · {segment.status}</span>
              {segment.cuts.filter((cut) => cut.status === "failed").map((cut) => (
                <div key={cut.index} className="render-error">
                  <span>第 {cut.index} 镜：{cut.error}</span>
                  <button type="button" onClick={() => handleRetry(segment.index, cut.index)}>重试该镜</button>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {exported && (
        <div className="episode-export">
          <video data-testid="episode-player" controls src={assetUrl(exported.clean_path)}>
            <track
              data-testid="episode-subtitles"
              kind="subtitles"
              src={assetUrl(exported.vtt_path)}
              srcLang="zh"
              label="中文字幕"
              ref={trackRef}
              default
            />
          </video>
          <button type="button" onClick={() => setShowSubtitles((value) => !value)}>
            {showSubtitles ? "隐藏字幕" : "显示字幕"}
          </button>
          <div className="download-links">
            <a href={assetUrl(exported.burned_path)} download>下载烧录版</a>
            <a href={assetUrl(exported.clean_path)} download>下载干净版</a>
            <a href={assetUrl(exported.srt_path)} download>下载 SRT</a>
          </div>
        </div>
      )}
    </div>
  );
}

export default EpisodeStudio;
