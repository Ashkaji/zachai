import React from "react";
import { History, X, Clock, ChevronRight } from "lucide-react";

export interface Snapshot {
  snapshot_id: string;
  created_at: string;
  source: string;
}

interface HistoryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  snapshots: Snapshot[];
  onSelectSnapshot: (snapId: string) => void;
  onHoverSnapshot?: (snapId: string | null) => void;
  onRestoreSnapshot: (snapId: string) => void;
  isLoading: boolean;
  activeSnapshotId: string | null;
  ghostMode: boolean;
  onClearDiff: () => void;
}

export const HistoryPanel: React.FC<HistoryPanelProps> = ({
  isOpen,
  onClose,
  snapshots,
  onSelectSnapshot,
  onHoverSnapshot,
  onRestoreSnapshot,
  isLoading,
  activeSnapshotId,
  ghostMode,
  onClearDiff,
}) => {
  return (
    <div
      className="za-glass"
      style={{
        width: isOpen ? "320px" : "0",
        overflow: "hidden",
        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        borderLeft: isOpen ? "1px solid var(--color-border-soft)" : "none",
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        position: "sticky",
        top: 0,
        zIndex: 40,
      }}
    >
      <div
        style={{
          padding: "var(--spacing-6)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid var(--color-border-soft)",
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: "1rem",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <History size={18} /> History
        </h3>
        <button
          onClick={onClose}
          className="za-btn za-btn--ghost"
          style={{ padding: "4px" }}
        >
          <X size={18} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "var(--spacing-4)" }}>
        {snapshots.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              color: "var(--color-text-muted)",
              marginTop: "2rem",
            }}
          >
            <Clock size={32} style={{ opacity: 0.2, marginBottom: "1rem" }} />
            <p>No snapshots yet.</p>
          </div>
        ) : (
          <div
            style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}
          >
            {snapshots.map((snap) => {
              const isActive = activeSnapshotId === snap.snapshot_id;
              return (
                <div key={snap.snapshot_id} style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <button
                    onClick={() => onSelectSnapshot(snap.snapshot_id)}
                    onMouseEnter={() => onHoverSnapshot?.(snap.snapshot_id)}
                    onMouseLeave={() => onHoverSnapshot?.(null)}
                    disabled={isLoading}
                    className={`za-card za-glass-hover ${
                      isActive ? "za-card--active" : ""
                    }`}
                    style={{
                      textAlign: "left",
                      width: "100%",
                      padding: "var(--spacing-3)",
                      border: "1px solid var(--color-border-soft)",
                      borderRadius: "var(--radius-md)",
                      cursor: "pointer",
                      position: "relative",
                      background: isActive ? "rgba(0, 120, 212, 0.1)" : "transparent",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <div
                        style={{
                          width: "8px",
                          height: "8px",
                          borderRadius: "50%",
                          background:
                            snap.source === "manual"
                              ? "var(--color-secondary)"
                              : "#0078d4",
                        }}
                      />
                      <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>
                        {new Date(snap.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: "0.7rem",
                        color: "var(--color-text-muted)",
                        marginLeft: "18px",
                        marginTop: "4px",
                      }}
                    >
                      {snap.source} • {snap.snapshot_id.slice(0, 8)}
                    </div>
                    <ChevronRight
                      size={14}
                      style={{
                        position: "absolute",
                        right: "12px",
                        top: "50%",
                        transform: "translateY(-50%)",
                        opacity: 0.3,
                      }}
                    />
                  </button>
                  {isActive && (
                    <button
                      onClick={() => onRestoreSnapshot(snap.snapshot_id)}
                      className="za-btn za-btn--primary"
                      style={{
                        fontSize: "0.75rem",
                        padding: "4px 12px",
                        height: "auto",
                        width: "fit-content",
                        alignSelf: "flex-end",
                        marginRight: "4px",
                        background: "rgba(229, 66, 66, 0.1)",
                        color: "#e54242",
                        border: "1px solid rgba(229, 66, 66, 0.2)",
                      }}
                    >
                      Restore this version
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {ghostMode && (
        <div
          style={{
            padding: "var(--spacing-4)",
            borderTop: "1px solid var(--color-border-soft)",
            background: "rgba(0, 120, 212, 0.05)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "8px",
            }}
          >
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#0078d4" }}>
              GHOST MODE ACTIVE
            </span>
            <button
              onClick={onClearDiff}
              className="za-btn za-btn--ghost"
              style={{ fontSize: "0.7rem", padding: "2px 6px", height: "auto" }}
            >
              Clear Diff
            </button>
          </div>
          <p
            style={{ fontSize: "0.7rem", margin: 0, color: "var(--color-text-muted)" }}
          >
            Visualizing changes against selected version.
          </p>
        </div>
      )}
    </div>
  );
};
