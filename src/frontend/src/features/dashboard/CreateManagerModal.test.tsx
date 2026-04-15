// @vitest-environment jsdom

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CreateManagerModal } from "./CreateManagerModal";

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

describe("CreateManagerModal", () => {
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

  it("submits manager creation request and calls success/close callbacks", async () => {
    createUserMock.mockResolvedValueOnce(undefined);

    await act(async () => {
      root.render(
        createElement(CreateManagerModal, {
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
        role: "Manager",
      },
      "bearer-token",
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clears error and form values after close and reopen", async () => {
    createUserMock.mockRejectedValueOnce(new Error("Already exists"));

    await act(async () => {
      root.render(
        createElement(CreateManagerModal, {
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
    await flushEffects();
    expect(document.body.textContent).toContain("Already exists");

    const cancelButton = Array.from(document.body.querySelectorAll("button")).find((btn) => btn.textContent === "Annuler");
    expect(cancelButton).not.toBeUndefined();
    await act(async () => {
      cancelButton!.click();
    });

    await act(async () => {
      root.render(
        createElement(CreateManagerModal, {
          isOpen: false,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });
    await act(async () => {
      root.render(
        createElement(CreateManagerModal, {
          isOpen: true,
          onClose,
          onSuccess,
          token: "bearer-token",
        }),
      );
    });

    expect(document.body.textContent).not.toContain("Already exists");
    expect(document.body.querySelector<HTMLInputElement>('input[name="username"]')?.value).toBe("");
    expect(document.body.querySelector<HTMLInputElement>('input[name="email"]')?.value).toBe("");
    expect(document.body.querySelector<HTMLInputElement>('input[name="firstName"]')?.value).toBe("");
    expect(document.body.querySelector<HTMLInputElement>('input[name="lastName"]')?.value).toBe("");
  });
});
