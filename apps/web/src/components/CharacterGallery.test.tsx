import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CharacterGallery from "./CharacterGallery";

const character = {
  id: 1,
  name: "林夏",
  biography: "调查记者",
  prompt_zh: "林夏，红绳学生装",
  prompt_en: "Lin Xia, red ribbon uniform",
  voice_prompt: "冷静女声",
  anchor_features: ["红绳", "学生装"],
  anchor_confirmed: false,
  images: [
    {
      id: 1,
      label: "front_full",
      status: "done",
      path: "assets/front.png",
      width: 1024,
      height: 1024,
      format: "png",
      workflow_id: "character_anchor_v1",
      error: null,
    },
    {
      id: 2,
      label: "avatar",
      status: "failed",
      path: "assets/avatar.png",
      width: 1024,
      height: 1024,
      format: "png",
      workflow_id: "character_views_v1",
      error: "生成失败",
    },
  ],
};

describe("CharacterGallery", () => {
  it("confirms anchors and retries individual images", () => {
    const onConfirm = vi.fn();
    const onRegenerate = vi.fn();
    render(
      <CharacterGallery
        characters={[character]}
        onConfirm={onConfirm}
        onRegenerate={onRegenerate}
      />,
    );

    expect(screen.getByText("调查记者")).toBeInTheDocument();
    expect(screen.getByText("冷静女声")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认锚点图" }));
    expect(onConfirm).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
    expect(onRegenerate).toHaveBeenCalledWith(2);
  });
});
