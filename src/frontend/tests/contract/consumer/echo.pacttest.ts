import { describe, it, expect } from "vitest";
import { createPactProvider } from "../support/pact-config";
import { createProviderState } from "../support/provider-states";
import { like } from "../support/consumer-helpers";
import { fetchEcho, setApiUrl } from "../support/demoApiClient";

describe("Echo contract", () => {
  it("matches echo payload contract", async () => {
    const provider = createPactProvider();

    await provider
      .addInteraction()
      .given(createProviderState("echo endpoint is available").state)
      .uponReceiving("a request for echo")
      .withRequest("GET", "/api/echo")
      .willRespondWith(200, (builder) => {
        builder.jsonBody({ message: like("ok") });
      })
      .executeTest(async (mockServer) => {
        setApiUrl(mockServer.url);
        const payload = await fetchEcho();
        expect(payload.message).toBe("ok");
      });
  });
});
