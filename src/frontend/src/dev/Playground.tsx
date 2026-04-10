import { Card, Metric, Badge, DataTable } from "../shared/ui/Primitives";
import { AzureTable, type AzureTableColumn } from "../shared/ui/AzureTable";
import { eventBus } from "../shared/notifications/NotificationContext";

const MOCK_DATA = Array.from({ length: 1000 }, (_, i) => ({
  id: `#${1000 + i}`,
  name: `Item ${i}`,
  status: i % 3 === 0 ? "Active" : i % 3 === 1 ? "Suspended" : "Pending",
  timestamp: new Date(Date.now() - i * 3600000).toLocaleString(),
}));

const COLUMNS: AzureTableColumn[] = [
  { key: "id", header: "ID", width: "80px" },
  { key: "name", header: "Name", width: "1fr" },
  { key: "status", header: "Status", width: "120px" },
  { key: "timestamp", header: "Timestamp", width: "200px" },
];

export function Playground() {
  const renderAzureCell = (item: any, column: AzureTableColumn) => {
    if (column.key === "status") {
      const tone = item.status === "Active" ? "success" : item.status === "Suspended" ? "error" : "primary";
      return <Badge tone={tone}>{item.status}</Badge>;
    }
    return item[column.key];
  };

  const handleTestNotification = (tier: "critical" | "informational" | "audit") => {
    eventBus.emit({
      tier,
      title: `Test ${tier.charAt(0).toUpperCase() + tier.slice(1)}`,
      body: `This is a test notification of tier ${tier} generated from the playground.`,
    });
  };

  const content = (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-8)", padding: "var(--spacing-8)", background: "var(--color-bg)", minHeight: "100%", color: "var(--color-text)" }}>
      <div>
        <h1 style={{ fontFamily: "var(--font-headline)", fontSize: "2rem", margin: "0 0 var(--spacing-2) 0" }}>Theme Playground</h1>
        <p style={{ color: "var(--color-text-muted)", margin: 0 }}>Validating the No-Line rule and atomic primitives.</p>
      </div>

      <div style={{ display: "grid", gap: "var(--spacing-6)", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        {/* Metric group inside a Card */}
        <Card title="Metrics Overview" subtitle="Business performance indicators">
          <div style={{ display: "grid", gap: "var(--spacing-4)", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}>
            <Metric label="Total Users" value="1,204" />
            <Metric label="Revenue" value="$42K" tone="success" />
            <Metric label="Errors" value="23" tone="error" />
          </div>
        </Card>

        {/* Badges and Buttons Card */}
        <Card title="Badges & Buttons" subtitle="Interactive and informational elements">
          <div style={{ display: "flex", gap: "var(--spacing-2)", flexWrap: "wrap", marginBottom: "var(--spacing-4)" }}>
            <Badge>Default</Badge>
            <Badge tone="primary">Primary</Badge>
            <Badge tone="success">Success</Badge>
            <Badge tone="error">Error</Badge>
          </div>
          <div style={{ display: "flex", gap: "var(--spacing-2)", flexWrap: "wrap" }}>
            <button className="za-btn za-btn--primary">Primary Action</button>
            <button className="za-btn">Secondary</button>
            <button className="za-btn za-btn--ghost">Ghost</button>
          </div>
        </Card>
      </div>
      
      <Card title="Notifications & Event Bus" subtitle="Test the unified notification provider">
        <div style={{ display: "flex", gap: "var(--spacing-4)" }}>
          <button className="za-btn za-btn--primary" onClick={() => handleTestNotification("informational")}>
            Trigger Informational
          </button>
          <button className="za-btn" style={{ background: "var(--color-error)", color: "white" }} onClick={() => handleTestNotification("critical")}>
            Trigger Critical
          </button>
          <button className="za-btn za-btn--ghost" onClick={() => handleTestNotification("audit")}>
            Trigger Audit (Silent)
          </button>
        </div>
      </Card>

      <Card title="Data Table (Legacy)" subtitle="Standard HTML Table with scroll">
        <DataTable
          columns={["ID", "Name", "Status", "Action"]}
          rows={[
            ["#1001", "John Doe", <Badge key="b1" tone="success">Active</Badge>, <button key="bt1" className="za-btn za-btn--ghost">Edit</button>],
            ["#1002", "Jane Smith", <Badge key="b2" tone="error">Suspended</Badge>, <button key="bt2" className="za-btn za-btn--ghost">Edit</button>],
            ["#1003", "Alice Johnson", <Badge key="b3" tone="primary">Pending</Badge>, <button key="bt3" className="za-btn za-btn--ghost">Edit</button>]
          ]}
        />
      </Card>

      <Card title="AzureTable (Virtualized)" subtitle="High-performance table with 1000 rows">
        <AzureTable
          columns={COLUMNS}
          data={MOCK_DATA}
          height={300}
          renderCell={renderAzureCell}
        />
      </Card>
    </div>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderRadius: "var(--radius-lg)", overflow: "hidden", border: "4px solid var(--color-surface-low)", height: "80vh" }}>
      <div data-theme="light" style={{ overflowY: "auto" }}>
        {content}
      </div>
      <div data-theme="dark" style={{ overflowY: "auto" }}>
        {content}
      </div>
    </div>
  );
}
