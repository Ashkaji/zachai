export type ApiHelper = {
  health: () => Promise<Response>;
};

export function createApiHelper(apiUrl: string): ApiHelper {
  return {
    health() {
      return fetch(`${apiUrl}/health`);
    },
  };
}
