/**
 * Vercel AI SDK provider adapter for Flint.
 *
 * Makes the orchestrator usable as a Vercel AI SDK compatible provider
 * so you can call `generateText({ model: provider('openai'), prompt })`.
 *
 * Zero external dependencies — uses duck-typed interfaces compatible
 * with the Vercel AI SDK's `LanguageModelV1` contract.
 */

import { OrchestratorClient } from "../client.js";
import { streamTaskUpdates } from "../streaming.js";
import { TaskState } from "../types.js";
import type { OrchestratorClientOptions, TaskRecord } from "../types.js";

// ── Duck-typed Vercel AI SDK interfaces ─────────────────────────────────────
// These match the shapes the AI SDK expects without importing it.

/** Mirrors `LanguageModelV1CallOptions` (subset we use). */
interface CallOptions {
  prompt: Array<{ role: string; content: unknown }>;
  mode?: { type: string };
  [key: string]: unknown;
}

/** Mirrors `LanguageModelV1FunctionToolCall`. */
interface ToolCall {
  toolCallType: "function";
  toolCallId: string;
  toolName: string;
  args: string;
}

/** Mirrors `LanguageModelV1FinishReason`. */
type FinishReason = "stop" | "length" | "content-filter" | "tool-calls" | "error" | "other";

/** Mirrors `LanguageModelV1GenerateResult`. */
interface GenerateResult {
  text: string | undefined;
  toolCalls: ToolCall[];
  finishReason: FinishReason;
  usage: { promptTokens: number; completionTokens: number };
  rawCall: { rawPrompt: unknown; rawSettings: Record<string, unknown> };
  rawResponse?: { headers?: Record<string, string> };
  warnings?: unknown[];
}

/** Mirrors stream part types from `LanguageModelV1StreamPart`. */
type StreamPart =
  | { type: "text-delta"; textDelta: string }
  | {
      type: "finish";
      finishReason: FinishReason;
      usage: { promptTokens: number; completionTokens: number };
    }
  | { type: "error"; error: unknown };

/** Mirrors `LanguageModelV1StreamResult`. */
interface StreamResult {
  stream: ReadableStream<StreamPart>;
  rawCall: { rawPrompt: unknown; rawSettings: Record<string, unknown> };
  rawResponse?: { headers?: Record<string, string> };
  warnings?: unknown[];
}

/** Mirrors the `LanguageModelV1` interface shape. */
interface LanguageModel {
  specificationVersion: "v1";
  provider: string;
  modelId: string;
  defaultObjectGenerationMode: undefined;
  doGenerate(options: CallOptions): PromiseLike<GenerateResult>;
  doStream(options: CallOptions): PromiseLike<StreamResult>;
}

// ── Provider types ──────────────────────────────────────────────────────────

export interface OrchestratorProviderOptions extends OrchestratorClientOptions {
  /** Orchestrator base URL. */
  baseUrl?: string;
  /** Poll interval in ms when waiting for task completion (default 1000). */
  pollInterval?: number;
  /** Max wait in ms for task completion (default 300 000). */
  taskTimeout?: number;
}

export type OrchestratorProvider = (modelId: string) => LanguageModel;

// ── Implementation ──────────────────────────────────────────────────────────

/**
 * Create a Vercel AI SDK–compatible provider backed by the orchestrator.
 *
 * ```ts
 * const provider = createOrchestratorProvider({ baseUrl: 'http://localhost:5156' });
 * const result = await generateText({ model: provider('openai'), prompt: 'Hello' });
 * ```
 */
export function createOrchestratorProvider(
  options: OrchestratorProviderOptions = {},
): OrchestratorProvider {
  const baseUrl = options.baseUrl ?? "http://localhost:5156";
  const pollInterval = options.pollInterval ?? 1_000;
  const taskTimeout = options.taskTimeout ?? 300_000;
  const client = new OrchestratorClient(baseUrl, options);

  return function provider(modelId: string): LanguageModel {
    return {
      specificationVersion: "v1",
      provider: "flint",
      modelId,
      defaultObjectGenerationMode: undefined,

      async doGenerate(callOptions: CallOptions): Promise<GenerateResult> {
        const prompt = extractPrompt(callOptions);
        const taskId = await client.submitTask(modelId, prompt);
        const task = await client.waitForTask(taskId, pollInterval, taskTimeout);

        const text = task.state === TaskState.Succeeded ? (task.result ?? "") : undefined;
        const finishReason: FinishReason =
          task.state === TaskState.Succeeded ? "stop" : "error";

        if (task.state !== TaskState.Succeeded) {
          return {
            text: undefined,
            toolCalls: [],
            finishReason,
            usage: { promptTokens: 0, completionTokens: 0 },
            rawCall: { rawPrompt: callOptions.prompt, rawSettings: {} },
            warnings: [
              { type: "other", message: `Task ${taskId} ended with state: ${task.state}` },
            ],
          };
        }

        return {
          text,
          toolCalls: [],
          finishReason,
          usage: { promptTokens: 0, completionTokens: 0 },
          rawCall: { rawPrompt: callOptions.prompt, rawSettings: {} },
        };
      },

      async doStream(callOptions: CallOptions): Promise<StreamResult> {
        const prompt = extractPrompt(callOptions);
        const taskId = await client.submitTask(modelId, prompt);

        const stream = new ReadableStream<StreamPart>({
          async start(controller) {
            let lastResult: string | null = null;
            try {
              for await (const update of streamTaskUpdates(baseUrl, taskId, {
                apiKey: options.apiKey,
              })) {
                if (update.result !== null && update.result !== lastResult) {
                  // Emit the delta — the new text since last update
                  const delta =
                    lastResult !== null
                      ? update.result.slice(lastResult.length)
                      : update.result;
                  if (delta) {
                    controller.enqueue({ type: "text-delta", textDelta: delta });
                  }
                  lastResult = update.result;
                }

                if (isTerminal(update)) {
                  controller.enqueue({
                    type: "finish",
                    finishReason:
                      update.state === TaskState.Succeeded ? "stop" : "error",
                    usage: { promptTokens: 0, completionTokens: 0 },
                  });
                  controller.close();
                  return;
                }
              }

              // Stream ended without a terminal event — close gracefully
              controller.enqueue({
                type: "finish",
                finishReason: "stop",
                usage: { promptTokens: 0, completionTokens: 0 },
              });
              controller.close();
            } catch (err) {
              controller.enqueue({ type: "error", error: err });
              controller.close();
            }
          },
        });

        return {
          stream,
          rawCall: { rawPrompt: callOptions.prompt, rawSettings: {} },
        };
      },
    };
  };
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Extract a single prompt string from the Vercel AI call options. */
function extractPrompt(options: CallOptions): string {
  const parts: string[] = [];
  for (const msg of options.prompt) {
    if (typeof msg.content === "string") {
      parts.push(msg.content);
    } else if (Array.isArray(msg.content)) {
      // Content parts array (e.g. [{ type: 'text', text: '...' }])
      for (const part of msg.content as Array<{ type: string; text?: string }>) {
        if (part.type === "text" && part.text) {
          parts.push(part.text);
        }
      }
    }
  }
  return parts.join("\n");
}

const TERMINAL_STATES = new Set<string>([
  TaskState.Succeeded,
  TaskState.Failed,
  TaskState.DeadLetter,
]);

function isTerminal(task: TaskRecord): boolean {
  return TERMINAL_STATES.has(task.state);
}
