import path from "node:path";
import { PactV4 } from "@pact-foundation/pact";

export function createPactProvider() {
  return new PactV4({
    consumer: "zachai-frontend",
    provider: "zachai-api",
    dir: path.resolve(process.cwd(), "pacts"),
    logLevel: "info",
  });
}
