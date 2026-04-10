import { useState } from 'react';
import { X, ChevronDown, ChevronUp, Info, DollarSign, RotateCcw } from 'lucide-react';

interface CostLineItem {
  description: string;
  tokens: number;
  rate_per_1k: number;
  cost_usd: number;
}

interface CostDetail {
  task_id: string;
  agent_type: string;
  model: string;
  provider: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  tool_costs?: { tool_name?: string; cost_usd: number }[];
  attempt: number;
  estimated?: boolean;
  cached_tokens?: number;
}

interface CostBreakdownModalProps {
  open: boolean;
  onClose: () => void;
  detail: CostDetail;
  costExplanation?: {
    breakdown: CostLineItem[];
    total_usd: number;
  };
  retryBreakdown?: {
    first_attempt_cost_usd: number;
    retry_cost_usd: number;
    attempts: number;
  };
}

function TokenBar({ input, output, cached }: { input: number; output: number; cached?: number }) {
  const total = input + output;
  if (total === 0) return <div className="h-3 bg-surface-3 rounded-full" />;
  const inputPct = (input / total) * 100;
  const cachedPct = cached ? (cached / total) * 100 : 0;
  const outputPct = (output / total) * 100;
  return (
    <div className="h-3 bg-surface-3 rounded-full overflow-hidden flex">
      {cachedPct > 0 && (
        <div className="h-full bg-cyan-500/60 transition-all duration-300" style={{ width: `${cachedPct}%` }} title={`Cached: ${(cached ?? 0).toLocaleString()}`} />
      )}
      <div className="h-full bg-blue-500/70 transition-all duration-300" style={{ width: `${inputPct - cachedPct}%` }} title={`Input: ${input.toLocaleString()}`} />
      <div className="h-full bg-green-500/70 transition-all duration-300" style={{ width: `${outputPct}%` }} title={`Output: ${output.toLocaleString()}`} />
    </div>
  );
}

export function CostBreakdownModal({ open, onClose, detail, costExplanation, retryBreakdown }: CostBreakdownModalProps) {
  const [showTools, setShowTools] = useState(false);
  if (!open) return null;

  const hasToolCosts = detail.tool_costs && detail.tool_costs.length > 0;
  const hasRetry = retryBreakdown && retryBreakdown.attempts > 1;
  const hasExplanation = costExplanation && costExplanation.breakdown.length > 0;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-surface-2 border border-border rounded-xl w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div>
            <h3 className="font-semibold text-sm">Cost Breakdown</h3>
            <p className="text-xs text-text-secondary mt-0.5">{detail.model} · {detail.provider}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-surface-3 text-text-secondary hover:text-text-primary transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Cost summary */}
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <p className="text-xs text-text-secondary uppercase tracking-wider">Total Cost</p>
              <p className="text-2xl font-bold text-success">${detail.cost_usd.toFixed(6)}</p>
            </div>
            <div className="flex-1">
              <p className="text-xs text-text-secondary uppercase tracking-wider">Total Tokens</p>
              <p className="text-2xl font-bold text-info">{detail.total_tokens.toLocaleString()}</p>
            </div>
            {detail.estimated && (
              <div className="px-2 py-1 rounded bg-warning/10 text-warning text-xs font-medium flex items-center gap-1">
                <Info className="w-3 h-3" /> Estimated
              </div>
            )}
          </div>

          {/* Token bar */}
          <div>
            <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
              <span>Token Distribution</span>
              <span>{detail.input_tokens.toLocaleString()} in / {detail.output_tokens.toLocaleString()} out</span>
            </div>
            <TokenBar input={detail.input_tokens} output={detail.output_tokens} cached={detail.cached_tokens} />
            <div className="flex items-center gap-4 mt-1 text-xs text-text-secondary">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500/70" /> Input</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500/70" /> Output</span>
              {detail.cached_tokens && detail.cached_tokens > 0 && (
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-cyan-500/60" /> Cached</span>
              )}
            </div>
          </div>

          {/* Cost explanation */}
          {hasExplanation && (
            <div>
              <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1">
                <DollarSign className="w-3 h-3" /> Cost Breakdown
              </h4>
              <div className="space-y-1">
                {costExplanation!.breakdown.filter(i => i.cost_usd > 0).map((item, i) => (
                  <div key={i} className="flex items-center justify-between text-sm py-1.5 px-3 rounded bg-surface-3/50">
                    <span className="text-text-secondary text-xs">{item.description}</span>
                    <span className="font-mono text-xs text-success">${item.cost_usd.toFixed(6)}</span>
                  </div>
                ))}
                {costExplanation!.breakdown.some(i => i.description.includes('estimated') || i.description.includes('Estimated')) && (
                  <div className="flex items-center gap-1 text-xs text-warning mt-1">
                    <Info className="w-3 h-3" /> Token counts are estimated
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tool costs */}
          {hasToolCosts && (
            <div>
              <button
                onClick={() => setShowTools(!showTools)}
                className="flex items-center gap-1 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors w-full"
              >
                {showTools ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                Tool Costs ({detail.tool_costs!.length})
              </button>
              {showTools && (
                <div className="mt-2 space-y-1">
                  {detail.tool_costs!.map((tc, i) => (
                    <div key={i} className="flex items-center justify-between text-sm py-1.5 px-3 rounded bg-surface-3/50">
                      <span className="text-text-secondary text-xs font-mono">{tc.tool_name || 'unknown'}</span>
                      <span className="font-mono text-xs text-success">${tc.cost_usd.toFixed(6)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Retry breakdown */}
          {hasRetry && (
            <div>
              <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-1">
                <RotateCcw className="w-3 h-3" /> Retry Cost ({retryBreakdown.attempts} attempts)
              </h4>
              <div className="space-y-1">
                <div className="flex items-center justify-between text-sm py-1.5 px-3 rounded bg-surface-3/50">
                  <span className="text-text-secondary text-xs">First attempt</span>
                  <span className="font-mono text-xs">${retryBreakdown.first_attempt_cost_usd.toFixed(6)}</span>
                </div>
                <div className="flex items-center justify-between text-sm py-1.5 px-3 rounded bg-error/10">
                  <span className="text-error text-xs">Retry cost</span>
                  <span className="font-mono text-xs text-error">${retryBreakdown.retry_cost_usd.toFixed(6)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="text-xs text-text-secondary border-t border-border pt-3 space-y-1">
            <div className="flex justify-between">
              <span>Agent</span>
              <span className="text-text-primary">{detail.agent_type}</span>
            </div>
            <div className="flex justify-between">
              <span>Attempt</span>
              <span>{detail.attempt}</span>
            </div>
            <div className="flex justify-between">
              <span>Task ID</span>
              <span className="font-mono">{detail.task_id.slice(0, 8)}...</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface CostBadgeProps {
  cost: number;
  tokens: number;
  model?: string;
  estimated?: boolean;
  onClick?: (e: React.MouseEvent) => void;
  className?: string;
}

export function CostBadge({ cost, tokens, model, estimated, onClick, className = '' }: CostBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 cursor-pointer hover:bg-surface-3 rounded px-1.5 py-0.5 transition-colors ${className}`}
      onClick={(e) => onClick?.(e)}
      title={model ? `${model} · ${tokens.toLocaleString()} tokens` : `${tokens.toLocaleString()} tokens`}
    >
      <span className="text-success font-mono text-xs">${cost.toFixed(6)}</span>
      {estimated && <span className="text-warning text-xs" title="Estimated tokens"><Info className="w-3 h-3" /></span>}
    </span>
  );
}
