import { useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type BackendStatus =
  | { kind: "loading" }
  | { kind: "ok"; version: string }
  | { kind: "error" };

async function fetchBackendStatus(signal: AbortSignal): Promise<BackendStatus> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/health`, { signal });
    if (!response.ok) return { kind: "error" };
    const body: { version: string } = await response.json();
    return { kind: "ok", version: body.version };
  } catch {
    return { kind: "error" };
  }
}

export function App() {
  const [status, setStatus] = useState<BackendStatus>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    void fetchBackendStatus(controller.signal).then(setStatus);
    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 p-8">
      <h1 className="text-4xl font-bold tracking-tight">Ideascope</h1>
      <p className="text-lg text-gray-600">See any idea, one click at a time.</p>
      <BackendBadge status={status} />
    </main>
  );
}

function BackendBadge({ status }: { status: BackendStatus }) {
  const label =
    status.kind === "loading"
      ? "Checking backend…"
      : status.kind === "ok"
        ? `Backend online (v${status.version})`
        : "Backend unreachable";

  return (
    <p className="text-sm text-gray-500" role="status">
      {label}
    </p>
  );
}
