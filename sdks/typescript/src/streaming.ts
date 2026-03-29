import type { TaskRecord } from "./types.js";

/**
 * Stream task updates via Server-Sent Events (SSE).
 *
 * Yields `TaskRecord` objects as the server pushes them. The iterator
 * completes when the server sends an `event: complete` or closes the
 * connection.
 *
 * Uses native `fetch` with streaming response body — no external
 * dependencies required. Works on Node.js 18+, Bun, and modern browsers.
 *
 * @param baseUrl  Orchestrator base URL (e.g. `http://localhost:5156`).
 * @param taskId   The task to stream updates for.
 * @param options  Optional headers (e.g. for API key).
 */
export async function* streamTaskUpdates(
  baseUrl: string,
  taskId: string,
  options?: { apiKey?: string },
): AsyncIterable<TaskRecord> {
  const url = `${baseUrl.replace(/\/+$/, "")}/tasks/${encodeURIComponent(taskId)}/stream`;
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
  };
  if (options?.apiKey) {
    headers["X-API-Key"] = options.apiKey;
  }

  const res = await fetch(url, { headers });

  if (!res.ok) {
    throw new Error(`SSE connection failed: HTTP ${res.status}`);
  }

  if (!res.body) {
    throw new Error("Response body is null — streaming not supported");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE messages (separated by double newline)
      const parts = buffer.split("\n\n");
      // Keep the last (potentially incomplete) part in the buffer
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const parsed = parseSseMessage(part);
        if (!parsed) continue;

        const { event, data } = parsed;

        // "complete" or "not_found" events signal the end of the stream
        if (event === "not_found" || event === "complete") {
          if (data) {
            yield JSON.parse(data) as TaskRecord;
          }
          return;
        }

        if (data) {
          yield JSON.parse(data) as TaskRecord;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Stream task updates via WebSocket.
 *
 * Yields `TaskRecord` objects until the WebSocket closes. Requires a
 * WebSocket global (Node.js 21+, Bun, browsers, or a polyfill).
 */
export async function* streamTaskUpdatesWs(
  baseUrl: string,
  taskId: string,
  options?: { apiKey?: string },
): AsyncIterable<TaskRecord> {
  const wsUrl = `${baseUrl.replace(/^http/, "ws").replace(/\/+$/, "")}/tasks/${encodeURIComponent(taskId)}/ws`;

  const protocols = options?.apiKey ? [options.apiKey] : undefined;
  const ws = new WebSocket(wsUrl, protocols);

  // Create a message queue that the async iterator can pull from
  const queue: TaskRecord[] = [];
  let done = false;
  let error: Error | undefined;
  let resolve: (() => void) | undefined;

  const waitForMessage = (): Promise<void> =>
    new Promise<void>((r) => {
      resolve = r;
    });

  ws.addEventListener("message", (event) => {
    const data = typeof event.data === "string" ? event.data : "";
    try {
      queue.push(JSON.parse(data) as TaskRecord);
    } catch {
      // skip non-JSON messages
    }
    resolve?.();
  });

  ws.addEventListener("close", () => {
    done = true;
    resolve?.();
  });

  ws.addEventListener("error", (evt) => {
    error = new Error(`WebSocket error: ${String(evt)}`);
    done = true;
    resolve?.();
  });

  // Wait for the connection to open
  await new Promise<void>((res, rej) => {
    ws.addEventListener("open", () => res());
    ws.addEventListener("error", () =>
      rej(new Error("WebSocket connection failed")),
    );
  });

  try {
    while (true) {
      if (queue.length > 0) {
        yield queue.shift()!;
        continue;
      }
      if (done) break;
      await waitForMessage();
      if (error) throw error;
    }

    // Drain remaining
    while (queue.length > 0) {
      yield queue.shift()!;
    }
  } finally {
    if (ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
  }
}

// ── SSE parsing helper ──────────────────────────────────────────────────────

function parseSseMessage(
  raw: string,
): { event: string | undefined; data: string | undefined } | undefined {
  let event: string | undefined;
  let data: string | undefined;

  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      const chunk = line.slice("data:".length).trim();
      data = data ? `${data}\n${chunk}` : chunk;
    }
    // Ignore id:, retry:, and comment lines
  }

  if (!event && !data) return undefined;
  return { event, data };
}
