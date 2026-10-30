import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StoryboardTimeline from "./StoryboardTimeline";

const storyboard = {
  episodes: [
    {
      episode: 1,
      segments: [
        {
          index: 1,
          duration_s: 7,
          cuts: [
            {
              index: 1,
              duration_s: 3,
              characters: ["林夏"],
              prompt: "林夏，红绳学生装；仓库中近景",
              camera: "推近",
              line_refs: [{ scene: 1, order: 2 }],
              scene_ref: null,
              keyframe_image: {
                path: "assets/frame.png",
                width: 1024,
                height: 768,
                format: "png",
                workflow_id: "storyboard_keyframe_v1",
              },
            },
          ],
        },
      ],
    },
  ],
};

describe("StoryboardTimeline", () => {
  it("shows cut details and opens a large keyframe", () => {
    render(<StoryboardTimeline storyboard={storyboard} />);

    expect(screen.getByText(/3 秒/)).toBeInTheDocument();
    expect(screen.getByText("推近")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /查看关键帧/ }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByAltText("关键帧大图")).toHaveAttribute(
      "src",
      "/api/v1/assets/assets/frame.png",
    );
  });
});
