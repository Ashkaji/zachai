/**
 * Ghost Mode Diff Worker — Story 12.2
 * Offloads Myers diff calculation to a background thread for UI smoothness.
 */

export type DiffChange = {
  type: 'add' | 'remove' | 'equal';
  value: string;
};

// Basic Myers Diff implementation
function diff(oldStr: string, newStr: string): DiffChange[] {
  const out: DiffChange[] = [];
  
  // Simple implementation using a naive approach for now
  // In a real app, use a robust library or a full Myers implementation
  // This is a placeholder for the logic.
  
  // Let's use a very simple word-based diff for demonstration
  const oldWords = oldStr.split(/(\s+)/);
  const newWords = newStr.split(/(\s+)/);
  
  let i = 0, j = 0;
  while (i < oldWords.length && j < newWords.length) {
    if (oldWords[i] === newWords[j]) {
      out.push({ type: 'equal', value: oldWords[i] });
      i++; j++;
    } else {
      // Look ahead to find matches
      let found = false;
      for (let k = j + 1; k < Math.min(j + 5, newWords.length); k++) {
        if (newWords[k] === oldWords[i]) {
          // Found match later in newStr -> additions
          for (let m = j; m < k; m++) {
            out.push({ type: 'add', value: newWords[m] });
          }
          out.push({ type: 'equal', value: oldWords[i] });
          i++; j = k + 1;
          found = true;
          break;
        }
      }
      if (!found) {
        // No match found soon -> removal
        out.push({ type: 'remove', value: oldWords[i] });
        i++;
      }
    }
  }
  
  // Remaining
  while (i < oldWords.length) {
    out.push({ type: 'remove', value: oldWords[i] });
    i++;
  }
  while (j < newWords.length) {
    out.push({ type: 'add', value: newWords[j] });
    j++;
  }
  
  return out;
}

self.onmessage = (e: MessageEvent) => {
  const { oldStr, newStr, requestId } = e.data;
  const result = diff(oldStr, newStr);
  self.postMessage({ result, requestId });
};
