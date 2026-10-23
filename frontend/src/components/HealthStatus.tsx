"use client";

import { useEffect, useState } from "react";

interface HealthData {
  status: string;
  service: string;
  environment: string;
  timestamp: string;
  components?: {
    database?: string;
    celery_broker?: string;
  };
}

export default function HealthStatus() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    fetch(`${apiUrl}/api/health/`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Unable to reach backend API");
        setLoading(false);
      });
  }, []);

  return (
    <div
      style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "8px",
        padding: "20px",
        marginTop: "20px",
      }}
    >
      <h3
        style={{
          fontSize: "1.1rem",
          marginBottom: "12px",
          color: "var(--text-primary)",
        }}
      >
        System Diagnostics & Readiness
      </h3>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "16px",
        }}
      >
        {/* Frontend Status */}
        <div
          style={{
            backgroundColor: "var(--bg-surface)",
            padding: "12px 16px",
            borderRadius: "6px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            Frontend Layer
          </div>
          <div
            style={{
              fontSize: "1.05rem",
              fontWeight: 600,
              color: "var(--success)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span
              style={{
                height: "8px",
                width: "8px",
                borderRadius: "50%",
                backgroundColor: "var(--success)",
              }}
            ></span>
            Online (Next.js 14)
          </div>
        </div>

        {/* Backend API Status */}
        <div
          style={{
            backgroundColor: "var(--bg-surface)",
            padding: "12px 16px",
            borderRadius: "6px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            Backend API
          </div>
          {loading ? (
            <div style={{ fontSize: "1.05rem", color: "var(--text-muted)" }}>
              Checking...
            </div>
          ) : error ? (
            <div
              style={{
                fontSize: "1.05rem",
                fontWeight: 600,
                color: "var(--warning)",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <span
                style={{
                  height: "8px",
                  width: "8px",
                  borderRadius: "50%",
                  backgroundColor: "var(--warning)",
                }}
              ></span>
              Standby ({error})
            </div>
          ) : (
            <div
              style={{
                fontSize: "1.05rem",
                fontWeight: 600,
                color: "var(--success)",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <span
                style={{
                  height: "8px",
                  width: "8px",
                  borderRadius: "50%",
                  backgroundColor: "var(--success)",
                }}
              ></span>
              {data?.status?.toUpperCase()} ({data?.service})
            </div>
          )}
        </div>

        {/* Database Status */}
        <div
          style={{
            backgroundColor: "var(--bg-surface)",
            padding: "12px 16px",
            borderRadius: "6px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            PostgreSQL / PostGIS
          </div>
          <div
            style={{
              fontSize: "1.05rem",
              fontWeight: 600,
              color:
                data?.components?.database === "healthy"
                  ? "var(--success)"
                  : "var(--text-secondary)",
            }}
          >
            {data?.components?.database?.toUpperCase() || "STANDBY"}
          </div>
        </div>

        {/* Celery / Redis Status */}
        <div
          style={{
            backgroundColor: "var(--bg-surface)",
            padding: "12px 16px",
            borderRadius: "6px",
            border: "1px solid var(--border-color)",
          }}
        >
          <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            Celery & Redis Broker
          </div>
          <div
            style={{
              fontSize: "1.05rem",
              fontWeight: 600,
              color:
                data?.components?.celery_broker === "healthy"
                  ? "var(--success)"
                  : "var(--text-secondary)",
            }}
          >
            {data?.components?.celery_broker?.toUpperCase() || "STANDBY"}
          </div>
        </div>
      </div>
    </div>
  );
}
