import type { Outline } from "../types";

function OutlineView({ outline }: { outline: Outline }) {
  return (
    <div className="asset-view">
      <section>
        <h2>改编大纲</h2>
        <p>{outline.synopsis}</p>
      </section>
      <section>
        <h2>角色</h2>
        <table>
          <thead><tr><th>角色</th><th>身份</th><th>戏份权重</th></tr></thead>
          <tbody>
            {outline.cast.map((member) => (
              <tr key={member.name}>
                <td>{member.name}</td>
                <td>{member.role}</td>
                <td>{Math.round(member.weight * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2>爽点节奏</h2>
        <div className="payoff-timeline">
          {outline.episode_beat.map((beat) => (
            <article key={beat.episode} className="payoff-item">
              <div>
                <strong>第 {beat.episode} 集 · {beat.payoff_type}</strong>
                <span>强度 {beat.payoff_intensity}/5</span>
              </div>
              <div
                className={`payoff-bar ${beat.payoff_intensity === 5 ? "major" : ""}`}
                style={{ width: `${beat.payoff_intensity * 20}%` }}
                aria-label={`第 ${beat.episode} 集爽点强度 ${beat.payoff_intensity}`}
              />
              <p>{beat.summary}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

export default OutlineView;
