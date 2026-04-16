import { test, expect } from "../support/fixtures";

test.describe("Authentication first flow", () => {
  test("Given a new visitor, when opening ZachAI, then login is required first", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("button", { name: "Se connecter avec Keycloak" })).toBeVisible();
    await expect(page).toHaveTitle(/zachai/i);
  });
});
