import { List } from "react-window";
import { type ReactNode, useMemo, type CSSProperties } from "react";

export interface AzureTableColumn {
  key: string;
  header: string;
  width?: string | number;
}

export interface AzureTableProps<T> {
  columns: AzureTableColumn[];
  data: T[];
  rowHeight?: number;
  height?: number;
  renderCell: (item: T, column: AzureTableColumn) => ReactNode;
}

interface RowData<T> {
  columns: AzureTableColumn[];
  data: T[];
  columnStyles: { width: string | number; padding: string }[];
  renderCell: (item: T, column: AzureTableColumn) => ReactNode;
}

const Row = <T,>({
  index,
  style,
  data,
  columns,
  columnStyles,
  renderCell,
}: {
  index: number;
  style: CSSProperties;
} & RowData<T>) => {
  const item = data[index];
  if (!item) return null;
  const isEven = index % 2 === 0;

  return (
    <div
      style={{
        ...style,
        display: "flex",
        alignItems: "center",
        background: isEven ? "var(--color-bg)" : "var(--color-surface-low)",
        transition: "background 0.2s ease",
        cursor: "default",
      }}
      className="za-table-row-hover"
    >
      {columns.map((col, colIndex) => (
        <div
          key={col.key}
          style={{
            width: columnStyles[colIndex]?.width,
            padding: columnStyles[colIndex]?.padding,
            fontSize: "0.9rem",
            color: "var(--color-text)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {renderCell(item, col)}
        </div>
      ))}
    </div>
  );
};

export function AzureTable<T>({
  columns,
  data,
  rowHeight = 56,
  height = 400,
  renderCell,
}: AzureTableProps<T>) {
  const columnStyles = useMemo(() => {
    return columns.map((col) => ({
      width: col.width || `${100 / columns.length}%`,
      padding: "var(--spacing-4)",
    }));
  }, [columns]);

  const rowData: RowData<T> = useMemo(
    () => ({
      columns,
      data,
      columnStyles,
      renderCell,
    }),
    [columns, data, columnStyles, renderCell]
  );

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100%",
        background: "var(--color-bg)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          background: "var(--color-surface-hi)",
          fontWeight: 700,
          fontSize: "0.75rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--color-text-muted)",
          zIndex: 1,
        }}
      >
        {columns.map((col, index) => (
          <div
            key={col.key}
            style={{
              width: columnStyles[index]?.width,
              padding: columnStyles[index]?.padding,
              textAlign: "left",
            }}
          >
            {col.header}
          </div>
        ))}
      </div>

      {/* Virtualized Body */}
      <div style={{ height }}>
        <List
          rowCount={data.length}
          rowHeight={rowHeight}
          rowComponent={Row as any}
          rowProps={rowData as any}
        />
      </div>

      <style>{`
        .za-table-row-hover:hover {
          background: var(--color-surface-hi) !important;
          box-shadow: inset 0 0 0 1px var(--color-outline-ghost);
        }
      `}</style>
    </div>
  );
}
