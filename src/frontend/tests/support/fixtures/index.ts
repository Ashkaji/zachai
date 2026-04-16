import { test as base } from "@playwright/test";
import { createUserFactory, type UserFactory } from "./factories/userFactory";
import { createAuthHelper, type AuthHelper } from "../helpers/authHelper";
import { createApiHelper, type ApiHelper } from "../helpers/apiHelper";

type Fixtures = {
  userFactory: UserFactory;
  authHelper: AuthHelper;
  apiHelper: ApiHelper;
};

export const test = base.extend<Fixtures>({
  userFactory: async ({}, use) => {
    const factory = createUserFactory();
    await use(factory);
    await factory.cleanup();
  },
  authHelper: async ({ page }, use) => {
    await use(createAuthHelper(page));
  },
  apiHelper: async ({}, use) => {
    await use(createApiHelper(process.env.API_URL ?? "http://localhost:8000"));
  },
});

export { expect } from "@playwright/test";
