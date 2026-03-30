import { describe, expect, it } from "vitest";
import {
  MAX_RECONNECT_ATTEMPTS,
  computeReconnectDelayMs,
  hasReconnectAttemptsRemaining,
  shouldRetryTicketHttpStatus,
} from "./reconnect-policy";

describe("reconnect policy", () => {
  it("retries only transient ticket statuses", () => {
    expect(shouldRetryTicketHttpStatus(429)).toBe(true);
    expect(shouldRetryTicketHttpStatus(500)).toBe(true);
    expect(shouldRetryTicketHttpStatus(503)).toBe(true);
    expect(shouldRetryTicketHttpStatus(599)).toBe(true);
    expect(shouldRetryTicketHttpStatus(401)).toBe(false);
    expect(shouldRetryTicketHttpStatus(408)).toBe(false);
    expect(shouldRetryTicketHttpStatus(403)).toBe(false);
    expect(shouldRetryTicketHttpStatus(409)).toBe(false);
    expect(shouldRetryTicketHttpStatus(499)).toBe(false);
  });

  it("uses exponential backoff with a 10s cap", () => {
    expect(computeReconnectDelayMs(0)).toBe(1000);
    expect(computeReconnectDelayMs(1)).toBe(2000);
    expect(computeReconnectDelayMs(2)).toBe(4000);
    expect(computeReconnectDelayMs(3)).toBe(8000);
    expect(computeReconnectDelayMs(4)).toBe(10000);
    expect(computeReconnectDelayMs(7)).toBe(10000);
    expect(computeReconnectDelayMs(0.9)).toBe(1000);
    expect(computeReconnectDelayMs(-1)).toBe(1000);
    expect(computeReconnectDelayMs(Number.NaN)).toBe(1000);
    expect(computeReconnectDelayMs(Number.POSITIVE_INFINITY)).toBe(1000);
  });

  it("stops after the max reconnect attempts", () => {
    expect(MAX_RECONNECT_ATTEMPTS).toBe(8);
    expect(hasReconnectAttemptsRemaining(0)).toBe(true);
    expect(hasReconnectAttemptsRemaining(7)).toBe(true);
    expect(hasReconnectAttemptsRemaining(8)).toBe(false);
    expect(hasReconnectAttemptsRemaining(9)).toBe(false);
    expect(hasReconnectAttemptsRemaining(-1)).toBe(true);
    expect(hasReconnectAttemptsRemaining(7.9)).toBe(true);
    expect(hasReconnectAttemptsRemaining(Number.NaN)).toBe(true);
    expect(hasReconnectAttemptsRemaining(Number.POSITIVE_INFINITY)).toBe(true);
  });
});
