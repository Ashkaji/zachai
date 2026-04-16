// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { InviteTeamMemberModal } from "./InviteTeamMemberModal";

const { createUserMock, notifyMock } = vi.hoisted(() => ({
  createUserMock: vi.fn(),
  notifyMock: vi.fn(),
}));

vi.mock("./dashboardApi", async () => {
  const actual = await vi.importActual<typeof import("./dashboardApi")>("./dashboardApi");
  return {
    ...actual,
    createUser: createUserMock,
  };
});

vi.mock("../../shared/notifications/NotificationContext", () => ({
  useNotifications: () => ({
    notify: notifyMock,
  }),
}));

beforeAll(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

async function flushEffects(): Promise<void> {
  await act(async () => {
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
  });
}

function setTextInputValue(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("InviteTeamMemberModal", () => {
  let container: HTMLDivElement;
  let root: Root;
  let onCloseCalls: number;
  let onSuccessCalls: number;
  let onClose: () => void;
  let onSuccess: () => void;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    onCloseCalls = 0;
    onSuccessCalls = 0;
    onClose = () => {
      onCloseCalls += 1;
    };
    onSuccess = () => {
      onSuccessCalls += 1;
    };
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
    expect(onSuccessCalls).toBe(1);
    expect(onCloseCalls).toBe(1);
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
    expect(onSuccessCalls).toBe(0);
    expect(onCloseCalls).toBe(0);
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

  it("trims input fields before submission", async () => {
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

    const usernameInput = document.body.querySelector<HTMLInputElement>('input[name="username"]');
    const emailInput = document.body.querySelector<HTMLInputElement>('input[name="email"]');
    const firstNameInput = document.body.querySelector<HTMLInputElement>('input[name="firstName"]');
    const lastNameInput = document.body.querySelector<HTMLInputElement>('input[name="lastName"]');

    await act(async () => {
      setTextInputValue(usernameInput!, "  user123  ");
      setTextInputValue(emailInput!, "  test@example.com  ");
      setTextInputValue(firstNameInput!, "  John  ");
      setTextInputValue(lastNameInput!, "  Doe  ");
    });
    await flushEffects();

    const form = document.body.querySelector("form");
    await act(async () => {
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(createUserMock).toHaveBeenCalledWith(
      expect.objectContaining({
        username: "user123",
        email: "test@example.com",
        firstName: "John",
        lastName: "Doe",
      }),
      "bearer-token",
    );
  });
});
