import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { ExpertDashboardStateContent, resolveExpertDashboardViewState } from "./RoleDashboards";

describe("ExpertDashboard view state", () => {
  it("returns loading before first fetch resolves", () => {
    expect(
      resolveExpertDashboardViewState({
        loading: true,
        error: "",
        tasksCount: 0,
      }),
    ).toBe("loading");
  });

  it("returns error when backend call fails", () => {
    expect(
      resolveExpertDashboardViewState({
        loading: false,
        error: "Forbidden",
        tasksCount: 0,
      }),
    ).toBe("error");
  });

  it("returns empty for successful empty list", () => {
    expect(
      resolveExpertDashboardViewState({
        loading: false,
        error: "",
        tasksCount: 0,
      }),
    ).toBe("empty");
  });

  it("returns success when tasks are present", () => {
    expect(
      resolveExpertDashboardViewState({
        loading: false,
        error: "",
        tasksCount: 2,
      }),
    ).toBe("success");
  });
});

describe("ExpertDashboard rendered state content", () => {
  it("renders loading message", () => {
    const html = renderToStaticMarkup(
      createElement("div", null, ExpertDashboardStateContent({ viewState: "loading", error: "", tasks: [] })),
    );
    expect(html).toContain("Chargement dashboard expert...");
  });

  it("renders backend error message", () => {
    const html = renderToStaticMarkup(
      createElement("div", null, ExpertDashboardStateContent({ viewState: "error", error: "Forbidden", tasks: [] })),
    );
    expect(html).toContain("Forbidden");
  });

  it("renders empty state message", () => {
    const html = renderToStaticMarkup(
      createElement("div", null, ExpertDashboardStateContent({ viewState: "empty", error: "", tasks: [] })),
    );
    expect(html).toContain("Aucune tache experte pour le moment.");
  });

  it("renders success table with task row", () => {
    const html = renderToStaticMarkup(
      createElement(
        "div",
        null,
        ExpertDashboardStateContent({
          viewState: "success",
          error: "",
          tasks: [
            {
              audio_id: 1,
              project_id: 2,
              project_name: "Project A",
              filename: "audio.wav",
              status: "transcribed",
              assigned_at: null,
              expert_id: "user-1",
              source: "label_studio",
              priority: "high",
            },
          ],
        }),
      ),
    );
    expect(html).toContain("audio.wav");
    expect(html).toContain("Project A");
    expect(html).toContain("label_studio");
  });
});
