import type { ActionBeat, Script, ScriptLine } from "../types";

type SceneContent =
  | (ActionBeat & { kind: "action" })
  | (ScriptLine & { kind: "line" });

function ScriptView({ script }: { script: Script }) {
  const colorByCharacter = new Map(
    script.cast.map((member, index) => [member.name, index % 4]),
  );

  return (
    <div className="asset-view script-view">
      {script.episodes.map((episode) => (
        <section key={episode.episode}>
          <div className="episode-heading">
            <h2>第 {episode.episode} 集</h2>
            <span>{episode.estimated_duration_s} 秒</span>
          </div>
          {episode.scenes.map((scene) => {
            const content: SceneContent[] = [
              ...scene.action_beats.map((beat) => ({ ...beat, kind: "action" as const })),
              ...scene.lines.map((line) => ({ ...line, kind: "line" as const })),
            ].sort((left, right) => left.order - right.order);
            return (
              <article key={scene.index} className="scene-card">
                <h3>第 {scene.index} 场 · {scene.heading}</h3>
                <div className="scene-content">
                  {content.map((item) =>
                    item.kind === "action" ? (
                      <p key={item.order} className="action-beat">{item.text}</p>
                    ) : (
                      <blockquote
                        key={item.order}
                        className={`script-line character-color-${colorByCharacter.get(item.character)}`}
                      >
                        <strong>{item.character}</strong>
                        <span>（{item.emotion}）</span>
                        {item.text}
                      </blockquote>
                    ),
                  )}
                </div>
              </article>
            );
          })}
        </section>
      ))}
    </div>
  );
}

export default ScriptView;
