import { useEffect, useState } from "react";

import { uploadProject } from "../api";
import type { LLMProvider, ProjectDetail, ProviderCapability } from "../types";

interface ProjectUploadProps {
  providers: LLMProvider[];
  onUploaded: (project: ProjectDetail) => void;
}

function ProjectUpload({ providers, onUploaded }: ProjectUploadProps) {
  const enabledProviders = providers.filter((provider) => provider.enabled);
  const [providerId, setProviderId] = useState("");
  const [imageProviderId, setImageProviderId] = useState("");
  const [videoProviderId, setVideoProviderId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function providersFor(capability: ProviderCapability) {
    return enabledProviders.filter((provider) =>
      (provider.capabilities ?? ["script"]).includes(capability),
    );
  }

  useEffect(() => {
    if (!providerId && providersFor("script").length > 0) {
      setProviderId(String(providersFor("script")[0].id));
    }
  }, [enabledProviders, providerId]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !providerId) {
      setError("请选择小说文件和剧本模型");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      onUploaded(
        await uploadProject(
          file,
          Number(providerId),
          imageProviderId ? Number(imageProviderId) : undefined,
          videoProviderId ? Number(videoProviderId) : undefined,
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  function renderSelect(
    label: string,
    value: string,
    onChange: (value: string) => void,
    capability: ProviderCapability,
    optional = false,
  ) {
    return (
      <label>
        {label}
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">{optional ? "暂不配置" : "请选择"}</option>
          {providersFor(capability).map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name} · {provider.model}
            </option>
          ))}
        </select>
      </label>
    );
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
      {renderSelect("剧本模型", providerId, setProviderId, "script")}
      {renderSelect("文生图模型", imageProviderId, setImageProviderId, "image", true)}
      {renderSelect("视频模型", videoProviderId, setVideoProviderId, "video", true)}
      <button type="submit" disabled={submitting || providersFor("script").length === 0}>
        {submitting ? "创建中…" : "创建项目"}
      </button>
      {error && <p role="alert" className="error-message">{error}</p>}
      <p className="form-hint">支持 PDF / DOCX / TXT。图像与视频模型将在后续阶段使用。</p>
    </form>
  );
}

export default ProjectUpload;
