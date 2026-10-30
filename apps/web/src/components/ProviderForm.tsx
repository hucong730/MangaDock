import { useState } from "react";

import { createProvider } from "../api";
import type { LLMProvider, ProviderCapability } from "../types";

const capabilityLabels: { value: ProviderCapability; label: string }[] = [
  { value: "script", label: "剧本生成" },
  { value: "image", label: "文生图" },
  { value: "video", label: "视频生成" },
];

function ProviderForm({ onCreated }: { onCreated: (provider: LLMProvider) => void }) {
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKeyEnv, setApiKeyEnv] = useState("");
  const [capabilities, setCapabilities] = useState<ProviderCapability[]>(["script"]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function toggleCapability(capability: ProviderCapability) {
    setCapabilities((current) =>
      current.includes(capability)
        ? current.filter((value) => value !== capability)
        : [...current, capability],
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (capabilities.length === 0) {
      setError("请至少选择一种模型能力");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      onCreated(
        await createProvider({
          name,
          base_url: baseUrl,
          model,
          api_key_env: apiKeyEnv,
          enabled: true,
          capabilities,
        }),
      );
      setName("");
      setBaseUrl("");
      setModel("");
      setApiKeyEnv("");
      setCapabilities(["script"]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Provider 创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="provider-form" onSubmit={handleSubmit}>
      <div className="provider-form-grid">
        <label>Provider 名称<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Base URL<input required type="url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label>
        <label>模型名称<input required value={model} onChange={(event) => setModel(event.target.value)} /></label>
        <label>密钥环境变量<input required value={apiKeyEnv} onChange={(event) => setApiKeyEnv(event.target.value)} /></label>
      </div>
      <fieldset className="capability-options">
        <legend>模型能力</legend>
        {capabilityLabels.map((item) => (
          <label key={item.value}>
            <input
              type="checkbox"
              checked={capabilities.includes(item.value)}
              onChange={() => toggleCapability(item.value)}
            />
            {item.label}
          </label>
        ))}
      </fieldset>
      <button type="submit" disabled={submitting}>{submitting ? "添加中…" : "添加 Provider"}</button>
      {error && <p role="alert" className="error-message">{error}</p>}
    </form>
  );
}

export default ProviderForm;
