import { describe, expect, it, vi } from "vitest";
import { fetchExpertTasks, fetchProjectStatus } from "./dashboardApi";

const apiJsonMock = vi.fn();

vi.mock("../../shared/api/zachaiApi", () => {
  return {
    apiJson: (...args: unknown[]) => apiJsonMock(...args),
    ApiError: class ApiError extends Error {
      readonly status: number;
      constructor(message: string, status: number) {
        super(message);
        this.status = status;
      }
    },
  };
});

describe("dashboardApi.fetchExpertTasks", () => {
  it("returns expert task payload from /v1/expert/tasks", async () => {
    const payload = [
      {
        audio_id: 1,
        project_id: 2,
        project_name: "Proj",
        filename: "a.wav",
        status: "transcribed",
        assigned_at: null,
        expert_id: null,
        source: "label_studio",
        priority: null,
      },
    ];
    apiJsonMock.mockResolvedValueOnce(payload);

    const out = await fetchExpertTasks("token-123");
    expect(out).toEqual(payload);
    expect(apiJsonMock).toHaveBeenCalledWith("/v1/expert/tasks", "token-123");
  });

  it("propagates ApiError on backend failure", async () => {
    const err = new Error("Forbidden") as Error & { status: number };
    err.status = 403;
    apiJsonMock.mockRejectedValueOnce(err);
    await expect(fetchExpertTasks("token-123")).rejects.toMatchObject({ message: "Forbidden", status: 403 });
  });
});

describe("dashboardApi.fetchProjectStatus", () => {
  it("fetches /v1/projects/:id/status and returns wrapper", async () => {
    const payload = {
      project_status: "active",
      audios: [
        { id: 10, filename: "test.wav", status: "uploaded", uploaded_at: "2026-04-02T12:00:00Z" },
      ],
    };
    apiJsonMock.mockResolvedValueOnce(payload);

    const out = await fetchProjectStatus(42, "token-42");
    expect(out).toEqual(payload);
    expect(apiJsonMock).toHaveBeenCalledWith("/v1/projects/42/status", "token-42");
  });
});
