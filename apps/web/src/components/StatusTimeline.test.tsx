import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import StatusTimeline from "./StatusTimeline";

const baseStage = {
  completed_items: 1,
  total_items: 1,
  attempt_count: 1,
  requires_attention: true,
  error: null,
};

describe("StatusTimeline", () => {
  it("shows anchor confirmation and stage three labels", () => {
    render(
      <StatusTimeline
        stages={[
          { ...baseStage, stage: "characters", status: "waiting_confirmation" },
          { ...baseStage, stage: "storyboard", status: "pending" },
        ]}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("等待锚点确认")).toBeInTheDocument();
    expect(screen.getByText("分镜等待中")).toBeInTheDocument();
  });
});
