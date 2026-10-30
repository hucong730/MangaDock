import { useState } from "react";

import type { Cut, Storyboard } from "../types";

function StoryboardTimeline({ storyboard }: { storyboard: Storyboard }) {
  const [selectedCut, setSelectedCut] = useState<Cut | null>(null);

  return (
    <div className="storyboard-timeline">
      {storyboard.episodes.map((episode) => (
        <section key={episode.episode}>
          <h2>第 {episode.episode} 集</h2>
          <div className="segment-list">
            {episode.segments.map((segment) => (
              <details key={segment.index} className="segment-card" open>
                <summary>第 {segment.index} 段 · {segment.duration_s} 秒</summary>
                <div className="cut-list">
                  {segment.cuts.map((cut) => (
                    <article key={cut.index} className="cut-card">
                      {cut.keyframe_image && (
                        <button
                          type="button"
                          className="keyframe-button"
                          onClick={() => setSelectedCut(cut)}
                          aria-label={`查看关键帧 ${episode.episode}-${segment.index}-${cut.index}`}
                        >
                          <img
                            src={`/api/v1/assets/${cut.keyframe_image.path}`}
                            alt={`第 ${cut.index} 镜关键帧`}
                          />
                        </button>
                      )}
                      <div>
                        <strong>第 {cut.index} 镜 · {cut.duration_s} 秒</strong>
                        <p>{cut.camera}</p>
                        <p>{cut.prompt}</p>
                        {cut.line_refs.length > 0 && (
                          <small>
                            台词：{cut.line_refs.map((ref) => `${ref.scene}:${ref.order}`).join("、")}
                          </small>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              </details>
            ))}
          </div>
        </section>
      ))}
      {selectedCut?.keyframe_image && (
        <dialog open className="keyframe-dialog" aria-label="关键帧大图">
          <button type="button" onClick={() => setSelectedCut(null)}>关闭</button>
          <img
            src={`/api/v1/assets/${selectedCut.keyframe_image.path}`}
            alt="关键帧大图"
          />
        </dialog>
      )}
    </div>
  );
}

export default StoryboardTimeline;
