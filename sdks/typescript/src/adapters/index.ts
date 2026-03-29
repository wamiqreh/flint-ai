/**
 * Re-exports all framework adapters.
 *
 * Prefer importing from the specific adapter subpath for tree-shaking:
 *   import { ... } from '@flintai/sdk/adapters/vercel-ai';
 */

export {
  createOrchestratorProvider,
  type OrchestratorProviderOptions,
  type OrchestratorProvider,
} from "./vercel-ai.js";

export {
  createOrchestratorMiddleware,
  type ExpressAdapterOptions,
} from "./express.js";

export {
  createTaskHandler,
  createWorkflowHandler,
  type NextjsAdapterOptions,
} from "./nextjs.js";
