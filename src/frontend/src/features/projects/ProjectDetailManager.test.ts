// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectDetailManager } from "./ProjectDetailManager";

const { authState, fetchProjectStatusMock, fetchProjectDetailMock } = vi.hoisted(() => ({
  authState: {
    isLoading: false,
    user: { access_token: "token" } as { access_token: string } | null,
  },
  fetchProjectStatusMock: vi.fn(),
  fetchProjectDetailMock: vi.fn(),
}));

vi.mock("../dashboard/dashboardApi", () => ({
  fetchProjectStatus: fetchProjectStatusMock,
  fetchProjectDetail: fetchProjectDetailMock,
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
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  });
}

describe("ProjectDetailManager", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    authState.isLoading = false;
    authState.user = { access_token: "token" };
    fetchProjectStatusMock.mockReset();
    fetchProjectDetailMock.mockReset();
    fetchProjectDetailMock.mockResolvedValue({
      id: 1,
      name: "Test Project",
      description: null,
      nature_id: 1,
      nature_name: "General",
      production_goal: null,
      status: "active",
      manager_id: "manager-1",
      label_studio_project_id: null,
      created_at: "2026-04-10T10:00:00Z",
      labels: [],
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("shows loading while OIDC context is loading", async () => {
    authState.isLoading = true;
    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    expect(container.textContent).toContain("Chargement du projet");
    expect(container.textContent).not.toContain("Détail Projet");
    expect(fetchProjectStatusMock).not.toHaveBeenCalled();
  });

  it("shows session error when there is no token after auth settled", async () => {
    authState.user = null;
    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    expect(container.textContent).toContain("Session indisponible");
    expect(fetchProjectStatusMock).not.toHaveBeenCalled();
  });

  it("shows loading then empty audios message after successful fetch", async () => {
    let resolveFetch!: (v: unknown) => void;
    const fetchPromise = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    fetchProjectStatusMock.mockReturnValueOnce(fetchPromise);

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    expect(container.textContent).toContain("Chargement du projet");

    await act(async () => {
      resolveFetch({ project_status: "active", audios: [] });
      await fetchPromise;
    });

    expect(container.textContent).toContain("Test Project");
    expect(container.textContent).toContain("Aucun fichier audio n'a été ajouté à ce projet.");
  });

  it("shows error message when fetch fails", async () => {
    fetchProjectStatusMock.mockRejectedValueOnce(new Error("Network down"));

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 5, onBack: () => {} }));
    });
    await flushEffects();
    expect(container.textContent).toContain("Network down");
  });

  it("renders audio rows and filters by status", async () => {
    fetchProjectStatusMock.mockResolvedValueOnce({
      project_status: "active",
      audios: [
        {
          id: 1,
          project_id: 1,
          filename: "a.wav",
          minio_path: "p/a",
          normalized_path: null,
          duration_s: null,
          status: "uploaded",
          validation_error: null,
          validation_attempted_at: null,
          uploaded_at: "2026-04-02T10:00:00Z",
          updated_at: "2026-04-02T10:00:00Z",
          assigned_to: null,
          assigned_at: null,
        },
        {
          id: 2,
          project_id: 1,
          filename: "b.wav",
          minio_path: "p/b",
          normalized_path: null,
          duration_s: null,
          status: "validated",
          validation_error: null,
          validation_attempted_at: null,
          uploaded_at: "2026-04-02T11:00:00Z",
          updated_at: "2026-04-02T11:00:00Z",
          assigned_to: "expert-1",
          assigned_at: "2026-04-02T11:30:00Z",
        },
      ],
    });

    await act(async () => {
      root.render(createElement(ProjectDetailManager, { projectId: 1, onBack: () => {} }));
    });
    await flushEffects();

    expect(container.textContent).toContain("a.wav");
    expect(container.textContent).toContain("b.wav");

    const filter = container.querySelector<HTMLSelectElement>("#status-filter");
    expect(filter).not.toBeNull();
    await act(async () => {
      filter!.value = "uploaded";
      filter!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.textContent).toContain("a.wav");
    expect(container.textContent).not.toContain("b.wav");
  });
});
