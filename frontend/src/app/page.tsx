import HealthStatus from "@/components/HealthStatus";

export default function Home() {
  const modules = [
    {
      name: "Cinema",
      desc: "Hall layouts, seat grid allocations, showtime dynamic decay",
    },
    {
      name: "Restaurants",
      desc: "Party covers, table allocations, shoulder-hour dining slots",
    },
    {
      name: "Surplus Food",
      desc: "Perishable batches, Magic Bags, FSSAI compliance, strict pickup windows",
    },
    {
      name: "Hotels",
      desc: "Room categories, calendar night-audit cutoffs, multi-night blocks",
    },
    {
      name: "Salons & Spas",
      desc: "Stylist rosters, service duration graphs, chair conflict locks",
    },
    {
      name: "Events",
      desc: "Tiered ticket quotas, gate verification, burst concurrency drops",
    },
    {
      name: "Travel",
      desc: "Bus & flight routes, schedules, passenger manifests, PNR generation",
    },
  ];

  return (
    <main
      style={{ maxWidth: "1000px", margin: "0 auto", padding: "40px 20px" }}
    >
      {/* Header */}
      <header
        style={{
          marginBottom: "32px",
          borderBottom: "1px solid var(--border-color)",
          paddingBottom: "24px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: "2rem",
                fontWeight: 700,
                letterSpacing: "-0.025em",
              }}
            >
              OneHopz
            </h1>
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "1rem",
                marginTop: "4px",
              }}
            >
              Perishable Inventory & Dynamic Yield Marketplace
            </p>
          </div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              backgroundColor: "rgba(99, 102, 241, 0.15)",
              color: "var(--brand-primary)",
              padding: "6px 14px",
              borderRadius: "20px",
              fontSize: "0.875rem",
              fontWeight: 600,
            }}
          >
            Milestone 1.3 Scaffold
          </div>
        </div>
      </header>

      {/* Notice Banner */}
      <section
        style={{
          backgroundColor: "rgba(245, 158, 11, 0.1)",
          border: "1px solid rgba(245, 158, 11, 0.3)",
          borderRadius: "8px",
          padding: "16px 20px",
          marginBottom: "28px",
        }}
      >
        <h2
          style={{
            fontSize: "1rem",
            fontWeight: 600,
            color: "var(--warning)",
            marginBottom: "4px",
          }}
        >
          Notice: Development & Engineering Scaffold Active
        </h2>
        <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>
          This page represents the initial repository and development
          environment foundation. Marketplace business models, payments, holds,
          orders, and customer booking workflows will be implemented in
          subsequent Level 1 & 2 milestones.
        </p>
      </section>

      {/* Health & Readiness Section */}
      <HealthStatus />

      {/* Planned Modules Overview */}
      <section style={{ marginTop: "40px" }}>
        <h2
          style={{
            fontSize: "1.25rem",
            fontWeight: 600,
            marginBottom: "16px",
            color: "var(--text-primary)",
          }}
        >
          Seven Core Business Modules (Architecture Blueprint)
        </h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "16px",
          }}
        >
          {modules.map((mod, idx) => (
            <div
              key={idx}
              style={{
                backgroundColor: "var(--bg-surface)",
                border: "1px solid var(--border-color)",
                borderRadius: "8px",
                padding: "16px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "8px",
                }}
              >
                <h3
                  style={{
                    fontSize: "1rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                  }}
                >
                  {mod.name}
                </h3>
                <span
                  style={{
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                    backgroundColor: "var(--bg-card)",
                    padding: "2px 8px",
                    borderRadius: "12px",
                  }}
                >
                  Module {idx + 1}
                </span>
              </div>
              <p
                style={{
                  fontSize: "0.85rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.4,
                }}
              >
                {mod.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer
        style={{
          marginTop: "60px",
          paddingTop: "20px",
          borderTop: "1px solid var(--border-color)",
          textAlign: "center",
          fontSize: "0.85rem",
          color: "var(--text-muted)",
        }}
      >
        OneHopz Architecture & Platform Foundation • Next.js 14 App Router +
        Django REST Framework + PostgreSQL/PostGIS
      </footer>
    </main>
  );
}
