import type { Page, Route } from "@playwright/test";

export async function interceptDashboard(page: Page, responseBody: unknown): Promise<void> {
  await page.route("**/dashboard/**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(responseBody),
    });
  });
}
