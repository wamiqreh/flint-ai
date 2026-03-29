import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types.js";

interface NodeInput {
  id: string;
  agentType: string;
  promptTemplate: string;
  maxRetries?: number;
  deadLetterOnFailure?: boolean;
  humanApproval?: boolean;
}

/**
 * Fluent builder for constructing `WorkflowDefinition` objects.
 *
 * @example
 * ```ts
 * const wf = new WorkflowBuilder("my-pipeline")
 *   .addNode({ id: "gen", agentType: "openai", promptTemplate: "Generate code" })
 *   .addNode({ id: "test", agentType: "dummy", promptTemplate: "Run tests", humanApproval: true })
 *   .addEdge("gen", "test")
 *   .build();
 * ```
 */
export class WorkflowBuilder {
  private readonly id: string;
  private readonly nodes: WorkflowNode[] = [];
  private readonly edges: WorkflowEdge[] = [];
  private readonly nodeIds = new Set<string>();

  constructor(workflowId: string) {
    this.id = workflowId;
  }

  /** Add a node to the workflow graph. */
  addNode(input: NodeInput): this {
    if (this.nodeIds.has(input.id)) {
      throw new Error(`Duplicate node id: "${input.id}"`);
    }

    this.nodeIds.add(input.id);
    this.nodes.push({
      Id: input.id,
      AgentType: input.agentType,
      PromptTemplate: input.promptTemplate,
      MaxRetries: input.maxRetries ?? 3,
      DeadLetterOnFailure: input.deadLetterOnFailure ?? true,
      HumanApproval: input.humanApproval ?? false,
    });

    return this;
  }

  /** Add a directed edge between two nodes. */
  addEdge(fromNodeId: string, toNodeId: string, condition?: string): this {
    if (!this.nodeIds.has(fromNodeId)) {
      throw new Error(`Unknown source node: "${fromNodeId}"`);
    }
    if (!this.nodeIds.has(toNodeId)) {
      throw new Error(`Unknown target node: "${toNodeId}"`);
    }

    this.edges.push({
      FromNodeId: fromNodeId,
      ToNodeId: toNodeId,
      ...(condition ? { Condition: condition } : {}),
    });

    return this;
  }

  /** Build and return the finalized workflow definition. */
  build(): WorkflowDefinition {
    if (this.nodes.length === 0) {
      throw new Error("Workflow must contain at least one node");
    }
    return {
      Id: this.id,
      Nodes: [...this.nodes],
      Edges: [...this.edges],
    };
  }
}
