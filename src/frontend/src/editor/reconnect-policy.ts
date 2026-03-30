export const MAX_RECONNECT_ATTEMPTS = 8;

export function shouldRetryTicketHttpStatus(status: number): boolean {
  // Retry only transient errors. Auth/permission/validation errors need user action.
  return status === 429 || status >= 500;
}

export function computeReconnectDelayMs(attemptIndex: number): number {
  return Math.min(1000 * 2 ** attemptIndex, 10000);
}

export function hasReconnectAttemptsRemaining(attemptsSoFar: number): boolean {
  return attemptsSoFar < MAX_RECONNECT_ATTEMPTS;
}
