import type { Page } from "@playwright/test";

export type AuthHelper = {
  loginAs: (role: string) => Promise<void>;
};

export function createAuthHelper(page: Page): AuthHelper {
  return {
    async loginAs(role: string) {
      await page.context().addCookies([
        {
          name: "zachai_test_role",
          value: role,
          domain: "localhost",
          path: "/",
          httpOnly: false,
          secure: false,
          sameSite: "Lax",
        },
      ]);
    },
  };
}
