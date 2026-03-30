export const MAX_RECONNECT_ATTEMPTS = 8;

export function shouldRetryTicketHttpStatus(status: number): boolean {
  // Retry only transient errors. Auth/permission/validation errors need user action.
  return status === 429 || status >= 500;
}

function toSafeAttemptCount(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.floor(value));
}

export function computeReconnectDelayMs(attemptIndex: number): number {
  const safeAttemptIndex = toSafeAttemptCount(attemptIndex);
  return Math.min(1000 * 2 ** safeAttemptIndex, 10000);
}

export function hasReconnectAttemptsRemaining(attemptsSoFar: number): boolean {
  const safeAttemptsSoFar = toSafeAttemptCount(attemptsSoFar);
  return safeAttemptsSoFar < MAX_RECONNECT_ATTEMPTS;
}
