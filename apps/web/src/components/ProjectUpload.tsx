import { useEffect, useState } from "react";

import { uploadProject } from "../api";
import type { LLMProvider, ProjectDetail } from "../types";

interface ProjectUploadProps {
  providers: LLMProvider[];
  onUploaded: (project: ProjectDetail) => void;
}

function ProjectUpload({ providers, onUploaded }: ProjectUploadProps) {
  const enabledProviders = providers.filter((provider) => provider.enabled);
  const [providerId, setProviderId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!providerId && enabledProviders.length > 0) {
      setProviderId(String(enabledProviders[0].id));
    }
  }, [enabledProviders, providerId]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !providerId) {
      setError("请选择小说文件和模型 Provider");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      onUploaded(await uploadProject(file, Number(providerId)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <label>
        小说文件
        <input
          type="file"
          accept=".pdf,.docx,.txt"
          onChange={(event) => setFile(event.target.files?.[0] || null)}
        />
      </label>
      <label>
        模型 Provider
        <select
          value={providerId}
          onChange={(event) => setProviderId(event.target.value)}
        >
          <option value="">请选择</option>
          {enabledProviders.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name} · {provider.model}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={submitting || enabledProviders.length === 0}>
        {submitting ? "创建中…" : "创建项目"}
      </button>
      {error && <p role="alert" className="error-message">{error}</p>}
      <p className="form-hint">支持 PDF / DOCX / TXT，文件不超过 20MB。</p>
    </form>
  );
}

export default ProjectUpload;
