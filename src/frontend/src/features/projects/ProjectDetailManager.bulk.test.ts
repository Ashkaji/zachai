// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectDetailManager } from "./ProjectDetailManager";

const { authState, fetchProjectStatusMock } = vi.hoisted(() => ({
  authState: {
    isLoading: false,
    user: { access_token: "token" } as { access_token: string } | null,
  },
  fetchProjectStatusMock: vi.fn(),
}));

vi.mock("../dashboard/dashboardApi", () => ({
  fetchProjectStatus: fetchProjectStatusMock,
  fetchProjectDetail: vi.fn().mockResolvedValue({
    id: 1,
    name: "Test Project",
    nature_name: "Nature 1",
    created_at: "2026-04-10T10:00:00Z",
    labels: []
  }),
  assignAudio: vi.fn().mockResolvedValue(undefined),
  validateAudio: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("react-oidc-context", () => ({
  useAuth: () => authState,
}));

vi.mock("../../auth/api-client", () => ({
  bearerForApi: () => (authState.user ? "bearer-token" : ""),
}));

beforeAll(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

async function flushEffects(): Promise<void> {
  await act(async () => {
    await new Promise<void>((resolve) => setTimeout(resolve, 10));
  });
}

describe("ProjectDetailManager Bulk Actions", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    authState.isLoading = false;
    authState.user = { access_token: "token" };
    fetchProjectStatusMock.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const mockAudios = [
    { id: 101, filename: "audio1.mp3", status: "uploaded", uploaded_at: "2026-04-10T10:00:00Z", project_id: 1, duration_s: 100, assigned_to: null },
    { id: 102, filename: "audio2.mp3", status: "transcribed", uploaded_at: "2026-04-10T11:00:00Z", project_id: 1, duration_s: 200, assigned_to: "user1" },
    { id: 103, filename: "audio3.mp3", status: "uploaded", uploaded_at: "2026-04-10T12:00:00Z", project_id: 1, duration_s: 300, assigned_to: null },
  ];

  it("renders checkboxes and shows bulk action bar when items are selected", async () => {
    fetchProjectStatusMock.mockResolvedValue({
      project_status: "active",
      audios: mockAudios,
    });

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    await flushEffects();

    const checkboxes = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    expect(checkboxes.length).toBe(4);

    await act(async () => {
      checkboxes[1]?.click();
    });
    await flushEffects();

    expect(container.textContent).toContain("1 élément(s) sélectionné(s)");
    expect(container.textContent).toContain("Assigner");
  });

  it("opens assign modal and reject modal", async () => {
    fetchProjectStatusMock.mockResolvedValue({
      project_status: "active",
      audios: mockAudios,
    });

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    await flushEffects();

    const checkboxes = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    await act(async () => {
      checkboxes[1]?.click();
    });
    await flushEffects();

    const assignBtn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.trim().includes("Assigner"),
    );
    expect(assignBtn).toBeDefined();
    await act(async () => {
      assignBtn?.click();
    });
    await flushEffects();

    expect(document.body.textContent).toContain("Assignation Groupée");
    expect(document.body.querySelector('input[placeholder*="ID Transcripteur"]')).not.toBeNull();

    const cancelBtn = Array.from(container.querySelectorAll("button")).find(b => b.textContent === "Annuler");
    await act(async () => {
      cancelBtn?.click();
    });
    await flushEffects();

    const rejectBtn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.trim().includes("Rejeter"),
    );
    expect(rejectBtn).toBeDefined();
    await act(async () => {
      rejectBtn?.click();
    });
    await flushEffects();

    expect(document.body.textContent).toContain("Rejet Groupé");
    expect(document.body.querySelector('select')).not.toBeNull();
  });

  it("selects only visible items when 'Select All' is clicked", async () => {
    fetchProjectStatusMock.mockResolvedValue({
      project_status: "active",
      audios: mockAudios,
    });

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    await flushEffects();

    const filter = container.querySelector<HTMLSelectElement>("#status-filter");
    await act(async () => {
      if (filter) {
        filter.value = "uploaded";
        filter.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await flushEffects();

    const checkboxes = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    await act(async () => {
      checkboxes[0]?.click();
    });
    await flushEffects();

    expect(container.textContent).toContain("2 élément(s) sélectionné(s)");
  });

  it("resets selection when filters or sort change", async () => {
    fetchProjectStatusMock.mockResolvedValue({
      project_status: "active",
      audios: mockAudios,
    });

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    await flushEffects();

    const checkboxes = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    await act(async () => {
      checkboxes[1]?.click();
    });
    await flushEffects();
    expect(container.textContent).toContain("1 élément(s) sélectionné(s)");

    // Reset on filter
    const filter = container.querySelector<HTMLSelectElement>("#status-filter");
    await act(async () => {
      if (filter) {
        filter.value = "transcribed";
        filter.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await flushEffects();
    expect(container.textContent).not.toContain("élément(s) sélectionné(s)");

    // Re-select
    const newCheckboxes = container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    await act(async () => {
      newCheckboxes[1]?.click();
    });
    await flushEffects();
    expect(container.textContent).toContain("1 élément(s) sélectionné(s)");

    // Reset on sort
    const sortSelect = container.querySelector<HTMLSelectElement>("#sort-field");
    await act(async () => {
      if (sortSelect) {
        sortSelect.value = "filename";
        sortSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await flushEffects();
    expect(container.textContent).not.toContain("élément(s) sélectionné(s)");
  });

  it("calculates and displays analytics correctly", async () => {
    fetchProjectStatusMock.mockResolvedValue({
      project_status: "active",
      audios: [
        { id: 1, status: "validated", duration_s: 3600, project_id: 1, uploaded_at: "2026-04-10T10:00:00Z", filename: "a.mp3", assigned_to: null },
        { id: 2, status: "transcribed", duration_s: 1800, project_id: 1, uploaded_at: "2026-04-10T11:00:00Z", filename: "b.mp3", assigned_to: null },
        { id: 3, status: "uploaded", duration_s: 600, project_id: 1, uploaded_at: "2026-04-10T12:00:00Z", filename: "c.mp3", assigned_to: null },
      ],
    });

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    await flushEffects();

    expect(container.textContent).toContain("33.3%");
    expect(container.textContent).toContain("01:40:00");
  });
});
