import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  fetchOutline,
  fetchProject,
  fetchProjectStatus,
  fetchScript,
  retryStage,
} from "../api";
import OutlineView from "../components/OutlineView";
import ScriptView from "../components/ScriptView";
import StatusTimeline from "../components/StatusTimeline";
import type { Outline, ProjectStatus, Script } from "../types";

function ProjectDetailPage() {
  const { id: rawId } = useParams();
  const projectId = Number(rawId);
  const [title, setTitle] = useState("项目详情");
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [script, setScript] = useState<Script | null>(null);
  const [error, setError] = useState("");
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    fetchProject(projectId)
      .then((project) => setTitle(project.title))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "项目加载失败"));
  }, [projectId]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const next = await fetchProjectStatus(projectId);
        if (!active) return;
        setStatus(next);
        setError("");
        const outlineStage = next.stages.find((stage) => stage.stage === "outline");
        const scriptStage = next.stages.find((stage) => stage.stage === "script");
        if (outlineStage?.status === "done") {
          setOutline(await fetchOutline(projectId));
        }
        if (scriptStage?.status === "done") {
          setScript(await fetchScript(projectId));
        }
        const hasFailedStage = next.stages.some((stage) => stage.status === "failed");
        const hasActiveStage = next.stages.some((stage) => ["pending", "running"].includes(stage.status));
        if (!hasFailedStage && hasActiveStage) {
          timer = setTimeout(poll, 2000);
        }
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : "状态加载失败");
          timer = setTimeout(poll, 2000);
        }
      }
    }

    poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [projectId, retryVersion]);

  async function handleRetry(stage: "outline" | "script") {
    setError("");
    try {
      await retryStage(projectId, stage);
      if (stage === "outline") {
        setOutline(null);
        setScript(null);
      } else {
        setScript(null);
      }
      setRetryVersion((version) => version + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试失败");
    }
  }

  return (
    <main className="page-shell">
      <Link to="/" className="back-link">← 返回项目列表</Link>
      <header className="detail-header">
        <p className="eyebrow">PROJECT #{projectId}</p>
        <h1>{title}</h1>
      </header>
      {error && <p role="alert" className="error-message">{error}</p>}
      <section className="panel">
        <h2>生成进度</h2>
        {status ? (
          <StatusTimeline stages={status.stages} onRetry={handleRetry} />
        ) : (
          <p>正在加载状态…</p>
        )}
      </section>
      {outline && <section className="panel"><OutlineView outline={outline} /></section>}
      {script && <section className="panel"><ScriptView script={script} /></section>}
    </main>
  );
}

export default ProjectDetailPage;
