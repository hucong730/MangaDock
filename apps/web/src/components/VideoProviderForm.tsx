import { useState } from "react";

import type { CreateVideoProviderInput, VideoProviderKind } from "../types";

interface VideoProviderFormProps {
  onCreate: (input: CreateVideoProviderInput) => void;
}

function VideoProviderForm({ onCreate }: VideoProviderFormProps) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<VideoProviderKind>("wan");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKeyEnv, setApiKeyEnv] = useState("");

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    onCreate({
      name,
      kind,
      base_url: baseUrl,
      model,
      api_key_env: apiKeyEnv,
      enabled: true,
      config_json: {},
    });
    setName("");
    setBaseUrl("");
    setModel("");
    setApiKeyEnv("");
  }

  return (
    <form className="provider-form" onSubmit={handleSubmit}>
      <label>名称<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <label>后端类型
        <select value={kind} onChange={(event) => setKind(event.target.value as VideoProviderKind)}>
          <option value="wan">Wan / ComfyUI</option>
          <option value="seedance">Seedance</option>
          <option value="minimax_h3">MiniMax H3</option>
        </select>
      </label>
      <label>Base URL<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} required /></label>
      <label>模型<input value={model} onChange={(event) => setModel(event.target.value)} required /></label>
      <label>密钥环境变量<input value={apiKeyEnv} onChange={(event) => setApiKeyEnv(event.target.value)} required /></label>
      <button type="submit">添加视频 Provider</button>
    </form>
  );
}

export default VideoProviderForm;
