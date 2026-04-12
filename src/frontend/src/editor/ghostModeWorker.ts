/**
 * Ghost Mode Diff Worker — Story 12.2
 * Character-based Myers Diff implementation for visual document history.
 */

export type DiffChange = {
  type: 'add' | 'remove' | 'equal';
  value: string;
};

/**
 * A robust character-level diff implementation.
 * Uses a simplified version of the Myers diff algorithm (LCS-based).
 */
function diff(oldStr: string, newStr: string): DiffChange[] {
  const n = oldStr.length;
  const m = newStr.length;

  // Initialise matrix with fixed dimensions
  const matrix: number[][] = [];
  for (let i = 0; i <= n; i++) {
    matrix[i] = new Array(m + 1).fill(0);
  }

  for (let i = 1; i <= n; i++) {
    const row = matrix[i]!;
    const prevRow = matrix[i - 1]!;
    for (let j = 1; j <= m; j++) {
      if (oldStr[i - 1] === newStr[j - 1]) {
        row[j] = (prevRow[j - 1] ?? 0) + 1;
      } else {
        row[j] = Math.max(prevRow[j] ?? 0, row[j - 1] ?? 0);
      }
    }
  }

  const result: DiffChange[] = [];
  let i = n;
  let j = m;

  while (i > 0 || j > 0) {
    const row = matrix[i]!;
    const prevRow = i > 0 ? matrix[i - 1]! : null;

    if (i > 0 && j > 0 && oldStr[i - 1] === newStr[j - 1]) {
      const val = oldStr[i - 1]!;
      const head = result[0];
      if (head && head.type === 'equal') {
        head.value = val + head.value;
      } else {
        result.unshift({ type: 'equal', value: val });
      }
      i--;
      j--;
    } else if (j > 0 && (i === 0 || (row[j - 1] ?? 0) >= (prevRow ? (prevRow[j] ?? 0) : 0))) {
      const val = newStr[j - 1]!;
      const head = result[0];
      if (head && head.type === 'add') {
        head.value = val + head.value;
      } else {
        result.unshift({ type: 'add', value: val });
      }
      j--;
    } else if (i > 0) {
      const val = oldStr[i - 1]!;
      const head = result[0];
      if (head && head.type === 'remove') {
        head.value = val + head.value;
      } else {
        result.unshift({ type: 'remove', value: val });
      }
      i--;
    }
  }

  return result;
}

self.onmessage = (e: MessageEvent) => {
  const { oldStr, newStr, requestId } = e.data;
  const s1 = typeof oldStr === 'string' ? oldStr : '';
  const s2 = typeof newStr === 'string' ? newStr : '';
  
  const result = diff(s1, s2);
  self.postMessage({ result, requestId });
};
