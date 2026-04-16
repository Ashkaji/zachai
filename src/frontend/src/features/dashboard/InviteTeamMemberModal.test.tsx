// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { InviteTeamMemberModal } from "./InviteTeamMemberModal";

const { createUserMock } = vi.hoisted(() => ({
  createUserMock: vi.fn(),
}));

vi.mock("./dashboardApi", async () => {
  const actual = await vi.importActual<typeof import("./dashboardApi")>("./dashboardApi");
  return {
    ...actual,
    createUser: createUserMock,
  };
});

beforeAll(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

async function flushEffects(): Promise<void> {
  await act(async () => {
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  });
}

describe("InviteTeamMemberModal", () => {
  let container: HTMLDivElement;
  let root: Root;
  let onClose: ReturnType<typeof vi.fn>;
  let onSuccess: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    onClose = vi.fn();
    onSuccess = vi.fn();
    createUserMock.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("submits Transcripteur creation by default", async () => {
    createUserMock.mockResolvedValueOnce(undefined);

    await act(async () => {
      root.render(
        createElement(InviteTeamMemberModal, {
          isOpen: true,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });

    const form = document.body.querySelector("form");
    expect(form).not.toBeNull();
    await act(async () => {
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(createUserMock).toHaveBeenCalledWith(
      {
        username: "",
        email: "",
        firstName: "",
        lastName: "",
        enabled: true,
        role: "Transcripteur",
      },
      "bearer-token",
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("submits Expert when Expert role is selected", async () => {
    createUserMock.mockResolvedValueOnce(undefined);

    await act(async () => {
      root.render(
        createElement(InviteTeamMemberModal, {
          isOpen: true,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });

    const expertRadio = Array.from(document.body.querySelectorAll('input[type="radio"]')).find(
      (el) => el.parentElement?.textContent?.includes("Expert"),
    ) as HTMLInputElement | undefined;
    expect(expertRadio).toBeDefined();
    await act(async () => {
      expertRadio!.click();
    });

    const form = document.body.querySelector("form");
    await act(async () => {
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(createUserMock).toHaveBeenCalledWith(
      expect.objectContaining({ role: "Expert" }),
      "bearer-token",
    );
  });

  it("does not offer Admin or Manager roles in the UI", async () => {
    await act(async () => {
      root.render(
        createElement(InviteTeamMemberModal, {
          isOpen: true,
          onClose,
          onSuccess,
          token: "t",
        }),
      );
    });
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bAdmin\b/);
    expect(text).not.toMatch(/\bManager\b/);
  });

  it("shows API error message on failure", async () => {
    createUserMock.mockRejectedValueOnce(new Error("Conflict user"));

    await act(async () => {
      root.render(
        createElement(InviteTeamMemberModal, {
          isOpen: true,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });

    const form = document.body.querySelector("form");
    await act(async () => {
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await flushEffects();
    expect(document.body.textContent).toContain("Conflict user");
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("clears error and form after close and reopen", async () => {
    createUserMock.mockRejectedValueOnce(new Error("fail"));

    await act(async () => {
      root.render(
        createElement(InviteTeamMemberModal, {
          isOpen: true,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });

    await act(async () => {
      document.body.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await flushEffects();
    expect(document.body.textContent).toContain("fail");

    const cancelButton = Array.from(document.body.querySelectorAll("button")).find((btn) => btn.textContent === "Annuler");
    await act(async () => {
      cancelButton!.click();
    });

    await act(async () => {
      root.render(
        createElement(InviteTeamMemberModal, {
          isOpen: false,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });
    await act(async () => {
      root.render(
        createElement(InviteTeamMemberModal, {
          isOpen: true,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });

    expect(document.body.textContent).not.toContain("fail");
    expect(document.body.querySelector<HTMLInputElement>('input[name="username"]')?.value).toBe("");
  });
});
