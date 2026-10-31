import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import VideoProviderForm from "./VideoProviderForm";

describe("VideoProviderForm", () => {
  it("creates a video provider", () => {
    const onCreate = vi.fn();
    render(<VideoProviderForm onCreate={onCreate} />);

    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "动作专用" } });
    fireEvent.change(screen.getByLabelText("Base URL"), { target: { value: "https://video.test" } });
    fireEvent.change(screen.getByLabelText("模型"), { target: { value: "seedance-pro" } });
    fireEvent.change(screen.getByLabelText("密钥环境变量"), { target: { value: "ARK_API_KEY" } });
    fireEvent.change(screen.getByLabelText("后端类型"), { target: { value: "seedance" } });
    fireEvent.click(screen.getByRole("button", { name: "添加视频 Provider" }));

    expect(onCreate).toHaveBeenCalledWith({
      name: "动作专用",
      kind: "seedance",
      base_url: "https://video.test",
      model: "seedance-pro",
      api_key_env: "ARK_API_KEY",
      enabled: true,
      config_json: {},
    });
  });
});
