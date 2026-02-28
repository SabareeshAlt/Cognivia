interface TelemetryEvent {
  event: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

const events: TelemetryEvent[] = [];

export function logTelemetry(event: string, metadata: Record<string, unknown> = {}): void {
  events.push({ event, metadata, timestamp: new Date().toISOString() });

  if (events.length > 200) {
    events.shift();
  }

  if (import.meta.env.DEV) {
    console.debug("[telemetry]", event, metadata);
  }
}

export function getTelemetryEvents(): TelemetryEvent[] {
  return [...events];
}

export function initializeClientTelemetry(): void {
  window.addEventListener("error", (event) => {
    logTelemetry("ui.error", {
      message: event.message,
      filename: event.filename,
      line: event.lineno,
      col: event.colno,
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    logTelemetry("ui.promise_rejection", {
      reason: String(event.reason),
    });
  });

  if ("PerformanceObserver" in window) {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.entryType === "largest-contentful-paint") {
          logTelemetry("webvitals.lcp", { value: entry.startTime, route: location.pathname });
        }
        if (entry.entryType === "layout-shift") {
          const shift = entry as PerformanceEntry & { value?: number; hadRecentInput?: boolean };
          if (!shift.hadRecentInput) {
            logTelemetry("webvitals.cls", { value: shift.value ?? 0, route: location.pathname });
          }
        }
      }
    });

    observer.observe({ type: "largest-contentful-paint", buffered: true });
    observer.observe({ type: "layout-shift", buffered: true });
  }
}
