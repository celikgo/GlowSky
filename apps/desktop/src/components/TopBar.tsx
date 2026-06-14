import { useEffect, useState } from "react";
import { api, type Health } from "../lib/api";

type Status = "checking" | "ok" | "down";

export function TopBar({ title }: { title: string }) {
  const [status, setStatus] = useState<Status>("checking");
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let live = true;
    const ping = async () => {
      try {
        const h = await api.health();
        if (live) {
          setHealth(h);
          setStatus("ok");
        }
      } catch {
        if (live) setStatus("down");
      }
    };
    ping();
    const t = setInterval(ping, 10000); // poll backend liveness
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  const label =
    status === "ok"
      ? `Backend online · ${health?.tools ?? 0} tools`
      : status === "down"
        ? "Backend offline"
        : "Connecting…";

  return (
    <header className="topbar">
      <div className="topbar__title">{title}</div>
      <div className="health" title={api.base}>
        <span
          className={`health__dot ${status === "ok" ? "health__dot--ok" : status === "down" ? "health__dot--down" : ""}`}
        />
        {label}
      </div>
    </header>
  );
}
