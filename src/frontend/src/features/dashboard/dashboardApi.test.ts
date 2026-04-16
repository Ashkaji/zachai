import { describe, expect, it, vi } from "vitest";
import { createUser, fetchExpertTasks, fetchProjectStatus } from "./dashboardApi";

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
        label_studio_project_id: 42,
        label_studio_url: "http://localhost:8090",
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

describe("dashboardApi.createUser", () => {
  it("posts manager payload to /v1/iam/users", async () => {
    apiJsonMock.mockResolvedValueOnce(undefined);

    await createUser(
      {
        username: "manager-1",
        email: "manager@example.com",
        firstName: "Marie",
        lastName: "Dupont",
        role: "Manager",
        enabled: true,
      },
      "token-iam",
    );

    expect(apiJsonMock).toHaveBeenCalledWith("/v1/iam/users", "token-iam", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: "manager-1",
        email: "manager@example.com",
        firstName: "Marie",
        lastName: "Dupont",
        role: "Manager",
        enabled: true,
      }),
    });
  });

  it("propagates backend errors", async () => {
    const err = new Error("Forbidden") as Error & { status: number };
    err.status = 403;
    apiJsonMock.mockRejectedValueOnce(err);

    await expect(
      createUser(
        {
          username: "manager-2",
          email: "manager2@example.com",
          firstName: "Anne",
          lastName: "Durand",
          role: "Manager",
        },
        "token-iam",
      ),
    ).rejects.toMatchObject({ message: "Forbidden", status: 403 });
  });
});
