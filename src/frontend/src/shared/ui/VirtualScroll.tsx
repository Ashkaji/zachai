import { List } from "react-window";
import type { ComponentType } from "react";

export function VirtualScrollContainer<T>({
  items,
  height,
  itemSize,
  rowComponent,
}: {
  items: T[];
  height: number;
  itemSize: number;
  rowComponent: ComponentType<any>;
}) {
  return (
    <div style={{ height }}>
      <List
        rowCount={items.length}
        rowHeight={itemSize}
        rowComponent={rowComponent as any}
        rowProps={items as any}
      />
    </div>
  );
}
