export type ProviderState = {
  state: string;
};

export function createProviderState(state: string): ProviderState {
  return { state };
}
