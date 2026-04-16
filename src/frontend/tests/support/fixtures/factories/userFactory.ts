import { faker } from "@faker-js/faker";

export type UserSeed = {
  email?: string;
  firstName?: string;
  lastName?: string;
};

export type UserPayload = Required<UserSeed> & { id: string };

export type UserFactory = {
  build: (seed?: UserSeed) => UserPayload;
  cleanup: () => Promise<void>;
};

export function createUserFactory(): UserFactory {
  const createdIds: string[] = [];

  return {
    build(seed = {}) {
      const user: UserPayload = {
        id: faker.string.uuid(),
        email: seed.email ?? faker.internet.email().toLowerCase(),
        firstName: seed.firstName ?? faker.person.firstName(),
        lastName: seed.lastName ?? faker.person.lastName(),
      };
      createdIds.push(user.id);
      return user;
    },
    async cleanup() {
      createdIds.length = 0;
    },
  };
}
