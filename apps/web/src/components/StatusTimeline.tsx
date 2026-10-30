import type { ProjectStage } from "../types";

interface StatusTimelineProps {
  stages: ProjectStage[];
  onRetry: (stage: "outline" | "script") => void;
}

const labels: Record<string, string> = {
  upload: "上传",
  outline: "大纲",
  script: "剧本",
};

function StatusTimeline({ stages, onRetry }: StatusTimelineProps) {
  return (
    <ol className="status-timeline">
      {stages.map((stage) => {
        const label = labels[stage.stage] || stage.stage;
        const stateText = {
          done: `${label}完成`,
          running: `${label}生成中`,
          failed: `${label}失败`,
          pending: `${label}等待中`,
        }[stage.status];
        return (
          <li key={stage.stage} className={`stage-item ${stage.status}`}>
            <span className="stage-icon" aria-hidden="true">
              {stage.status === "done" ? "✓" : stage.status === "running" ? "↻" : stage.status === "failed" ? "!" : "·"}
            </span>
            <div>
              <strong>{stateText}</strong>
              {stage.total_items > 0 && (
                <p>进度 {stage.completed_items}/{stage.total_items}</p>
              )}
              {stage.error && <p className="error-message">{stage.error}</p>}
              {stage.status === "failed" && stage.stage !== "upload" && (
                <button
                  type="button"
                  onClick={() => onRetry(stage.stage as "outline" | "script")}
                >
                  重试该阶段
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default StatusTimeline;
