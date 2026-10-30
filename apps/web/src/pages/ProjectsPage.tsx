import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { fetchHealth, fetchProjects, fetchProviders } from "../api";
import ProviderForm from "../components/ProviderForm";
import ProjectUpload from "../components/ProjectUpload";
import type { HealthResponse, LLMProvider, ProjectSummary } from "../types";

type LoadState<T> =
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error" };

function ProjectsPage() {
  const navigate = useNavigate();
  const [health, setHealth] = useState<LoadState<HealthResponse>>({ status: "loading" });
  const [providers, setProviders] = useState<LoadState<LLMProvider[]>>({ status: "loading" });
  const [projects, setProjects] = useState<LoadState<ProjectSummary[]>>({ status: "loading" });

  useEffect(() => {
    let active = true;
    fetchHealth()
      .then((data) => active && setHealth({ status: "success", data }))
      .catch(() => active && setHealth({ status: "error" }));
    fetchProviders()
      .then((data) => active && setProviders({ status: "success", data }))
      .catch(() => active && setProviders({ status: "error" }));
    fetchProjects()
      .then((data) => active && setProjects({ status: "success", data }))
      .catch(() => active && setProjects({ status: "error" }));
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="page-shell">
      <header className="hero">
        <p className="eyebrow">MANGADOCK · 漫坞</p>
        <h1>AI 漫剧流水线</h1>
        <p>上传小说，获得结构化改编大纲与分集剧本。</p>
      </header>

      <section className="panel" aria-labelledby="health-heading">
        <div className="section-heading">
          <h2 id="health-heading">服务状态</h2>
          {health.status === "success" && <span className="status-dot" />}
        </div>
        {health.status === "loading" && <p>正在检查服务状态…</p>}
        {health.status === "error" && <p role="alert" className="error-message">健康检查失败，请确认 API 与数据库已启动。</p>}
        {health.status === "success" && (
          <div className="health-details"><strong>服务正常</strong><span>数据库连接正常</span></div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading"><h2>新建漫剧项目</h2></div>
        {providers.status === "success" ? (
          <ProjectUpload
            providers={providers.data}
            onUploaded={(project) => navigate(`/projects/${project.id}`)}
          />
        ) : providers.status === "error" ? (
          <p role="alert" className="error-message">Provider 加载失败，请稍后重试。</p>
        ) : (
          <p>正在加载 Provider…</p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div><p className="section-kicker">PROJECTS</p><h2>我的项目</h2></div>
          {projects.status === "success" && <span className="count-badge">{projects.data.length}</span>}
        </div>
        {projects.status === "loading" && <p>正在加载项目…</p>}
        {projects.status === "error" && <p role="alert" className="error-message">项目加载失败</p>}
        {projects.status === "success" && projects.data.length === 0 && <p>暂无项目，请先上传小说。</p>}
        {projects.status === "success" && (
          <div className="project-list">
            {projects.data.map((project) => (
              <Link key={project.id} to={`/projects/${project.id}`} className="project-card">
                <strong>{project.title}</strong>
                <span>{project.source_filename}</span>
                <span>{project.stages.find((stage) => stage.stage === "script")?.status === "done" ? "剧本已完成" : "生成中"}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="providers-heading">
        <div className="section-heading"><h2 id="providers-heading">模型 Provider</h2></div>
        {providers.status === "success" && (
          <ProviderForm
            onCreated={(provider) =>
              setProviders({ status: "success", data: [...providers.data, provider] })
            }
          />
        )}
        {providers.status === "success" && providers.data.length === 0 && (
          <div className="empty-state"><strong>暂未配置 Provider</strong></div>
        )}
        {providers.status === "success" && providers.data.length > 0 && (
          <div className="table-wrapper">
            <table>
              <thead><tr><th>名称</th><th>Base URL</th><th>模型</th><th>能力</th><th>密钥环境变量</th><th>状态</th></tr></thead>
              <tbody>
                {providers.data.map((provider) => (
                  <tr key={provider.id}>
                    <td>{provider.name}</td><td>{provider.base_url}</td><td>{provider.model}</td>
                    <td>{(provider.capabilities ?? ["script"]).map((capability) => (
                      <span key={capability} className={`capability-badge ${capability}`}>{capability}</span>
                    ))}</td>
                    <td><code>{provider.api_key_env}</code></td><td>{provider.enabled ? "已启用" : "已停用"}</td>
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

export default ProjectsPage;
