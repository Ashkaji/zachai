import { useState } from "react";

export type BatchResult = {
  id: number | string;
  success: boolean;
  error?: string;
};

export type BatchStatus = "idle" | "processing" | "completed";

export function useBatchAction<T>(
  actionFn: (id: T) => Promise<void>
) {
  const [status, setStatus] = useState<BatchStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [total, setTotal] = useState(0);
  const [results, setBatchResults] = useState<BatchResult[]>([]);

  const runBatch = async (ids: T[]) => {
    setStatus("processing");
    setProgress(0);
    setTotal(ids.length);
    const newResults: BatchResult[] = [];

    // Simple sequential execution if concurrency is 1
    // For now, we use sequential to be safe as requested
    for (const id of ids) {
      try {
        await actionFn(id);
        newResults.push({ id: String(id), success: true });
      } catch (e) {
        newResults.push({ 
          id: String(id), 
          success: false, 
          error: e instanceof Error ? e.message : "Error" 
        });
      }
      setProgress((prev) => prev + 1);
    }

    setBatchResults(newResults);
    setStatus("completed");
  };

  const reset = () => {
    setStatus("idle");
    setProgress(0);
    setTotal(0);
    setBatchResults([]);
  };

  return {
    status,
    progress,
    total,
    results,
    runBatch,
    reset
  };
}
