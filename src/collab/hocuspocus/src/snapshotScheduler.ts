export type SnapshotDispatch = (documentId: number) => Promise<void> | void;

type TimerHandle = ReturnType<typeof setTimeout>;

type DocumentState = {
  timer: TimerHandle | null;
  inFlight: boolean;
  queued: boolean;
};

export function createIdleSnapshotScheduler(idleMs: number, dispatch: SnapshotDispatch) {
  const states = new Map<number, DocumentState>();

  const ensure = (documentId: number): DocumentState => {
    const existing = states.get(documentId);
    if (existing) return existing;
    const created: DocumentState = { timer: null, inFlight: false, queued: false };
    states.set(documentId, created);
    return created;
  };

  const clearTimer = (state: DocumentState) => {
    if (!state.timer) return;
    clearTimeout(state.timer);
    state.timer = null;
  };

  const scheduleTimer = (documentId: number, state: DocumentState) => {
    clearTimer(state);
    state.timer = setTimeout(() => {
      state.timer = null;
      void fire(documentId);
    }, idleMs);
  };

  const fire = async (documentId: number) => {
    const state = ensure(documentId);
    if (state.inFlight) {
      state.queued = true;
      return;
    }
    state.inFlight = true;
    try {
      await dispatch(documentId);
    } finally {
      state.inFlight = false;
      if (state.queued) {
        state.queued = false;
        scheduleTimer(documentId, state);
      }
    }
  };

  const onUpdate = (documentId: number) => {
    const state = ensure(documentId);
    if (state.inFlight) {
      state.queued = true;
      return;
    }
    scheduleTimer(documentId, state);
  };

  const purge = (documentId: number) => {
    const state = states.get(documentId);
    if (!state) return;
    clearTimer(state);
    state.queued = false;
    states.delete(documentId);
  };

  const dispose = () => {
    for (const state of states.values()) {
      clearTimer(state);
    }
    states.clear();
  };

  return { onUpdate, purge, dispose };
}