import { useEffect, useState } from "react";

import { fetchHealth, fetchProviders } from "./api";
import type { HealthResponse, LLMProvider } from "./types";

type LoadState<T> =
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error" };

function App() {
  const [health, setHealth] = useState<LoadState<HealthResponse>>({
    status: "loading",
  });
  const [providers, setProviders] = useState<LoadState<LLMProvider[]>>({
    status: "loading",
  });

  useEffect(() => {
    let active = true;

    fetchHealth()
      .then((data) => {
        if (active) {
          setHealth({ status: "success", data });
        }
      })
      .catch(() => {
        if (active) {
          setHealth({ status: "error" });
        }
      });

    fetchProviders()
      .then((data) => {
        if (active) {
          setProviders({ status: "success", data });
        }
      })
      .catch(() => {
        if (active) {
          setProviders({ status: "error" });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="page-shell">
      <header className="hero">
        <p className="eyebrow">MANGADOCK · 漫坞</p>
        <h1>AI 漫剧流水线</h1>
        <p>模型可插拔，创作流程清晰可见。</p>
      </header>

      <section className="panel" aria-labelledby="health-heading">
        <div className="section-heading">
          <h2 id="health-heading">服务状态</h2>
          {health.status === "success" && <span className="status-dot" />}
        </div>
        {health.status === "loading" && <p>正在检查服务状态…</p>}
        {health.status === "error" && (
          <p role="alert" className="error-message">
            健康检查失败，请确认 API 与数据库已启动。
          </p>
        )}
        {health.status === "success" && (
          <div className="health-details">
            <strong>服务正常</strong>
            <span>数据库连接正常</span>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="providers-heading">
        <div className="section-heading">
          <div>
            <p className="section-kicker">MODEL CONNECTIONS</p>
            <h2 id="providers-heading">LLM Providers</h2>
          </div>
          {providers.status === "success" && (
            <span className="count-badge">{providers.data.length}</span>
          )}
        </div>
        {providers.status === "loading" && <p>正在加载 Provider…</p>}
        {providers.status === "error" && (
          <p role="alert" className="error-message">
            Provider 加载失败，请稍后重试。
          </p>
        )}
        {providers.status === "success" && providers.data.length === 0 && (
          <div className="empty-state">
            <strong>暂未配置 Provider</strong>
            <p>通过 API 添加模型连接后，会显示在这里。</p>
          </div>
        )}
        {providers.status === "success" && providers.data.length > 0 && (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>Base URL</th>
                  <th>模型</th>
                  <th>密钥环境变量</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {providers.data.map((provider) => (
                  <tr key={provider.id}>
                    <td data-label="名称">{provider.name}</td>
                    <td data-label="Base URL">{provider.base_url}</td>
                    <td data-label="模型">{provider.model}</td>
                    <td data-label="密钥环境变量">
                      <code>{provider.api_key_env}</code>
                    </td>
                    <td data-label="状态">
                      <span
                        className={
                          provider.enabled
                            ? "provider-status enabled"
                            : "provider-status"
                        }
                      >
                        {provider.enabled ? "已启用" : "已停用"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

export default App;
