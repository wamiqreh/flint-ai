/**
 * Example: Using Flint as a Vercel AI SDK provider.
 *
 * This lets you use the orchestrator with `generateText` and `streamText`
 * from the Vercel AI SDK, treating agent types as model identifiers.
 *
 * Prerequisites:
 *   npm install ai @flintai/sdk
 */

import { generateText, streamText } from "ai";
import { createOrchestratorProvider } from "@flintai/sdk/adapters/vercel-ai";

const provider = createOrchestratorProvider({
  baseUrl: "http://localhost:5156",
  apiKey: "your-api-key",
});

// ── Generate text (submit + poll until complete) ────────────────────────────

async function generateExample() {
  const result = await generateText({
    model: provider("openai"),
    prompt: "Write a TypeScript function that reverses a string.",
  });

  console.log("Generated text:", result.text);
}

// ── Stream text (SSE streaming) ─────────────────────────────────────────────

async function streamExample() {
  const result = await streamText({
    model: provider("openai"),
    prompt: "Explain the observer pattern in software design.",
  });

  for await (const chunk of result.textStream) {
    process.stdout.write(chunk);
  }
  console.log("\n--- stream complete ---");
}

// Run examples
generateExample().catch(console.error);
streamExample().catch(console.error);
