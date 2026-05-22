// TypeScript type definitions for miser-client v1.5 (P1 #7)

export interface MiserStatus {
  model: string;
  model_family: string;
  tokens_saved_est: number;
  queue: { queue_size: number; max_size: number; total_queued: number };
  cache: { entries: number; hits: number; misses: number; hit_rate: number };
  prefetch: { prefetch_count: number; hit_count: number };
  breaker: string;
}

export interface FileInfo {
  exists: boolean;
  path: string;
  is_file?: boolean;
  is_dir?: boolean;
  size?: number;
}

export interface CondenseResult {
  digest: string;
  savings?: {
    original_chars: number;
    condensed_chars: number;
    tokens_saved: number;
    reduction_pct: number;
  };
}

export interface BatchItem {
  type: "run" | "read" | "grep" | "outline" | "tree" | "exists" | "write" | "ask";
  cmd?: string;
  path?: string;
  pattern?: string;
  context?: number;
  depth?: number;
  content?: string;
  task?: string;
}

export interface BatchResult {
  type: string;
  result?: any;
  data?: any;
  error?: string;
}

export interface MiserClient {
  // Zero-LLM ops (instant, deterministic)
  outline(path: string): Promise<string>;
  grep(path: string, pattern: string, ctx?: number): Promise<string>;
  tree(path?: string, depth?: number): Promise<string>;
  exists(path: string): Promise<FileInfo>;
  read(path: string, limit?: number): Promise<string>;
  write(path: string, content: string): Promise<string>;
  run(cmd: string): Promise<string>;

  // Local-LLM ops (zero API cost)
  ask(task: string, maxTokens?: number): Promise<string>;
  codegen(task: string, lang?: string): Promise<string>;
  explain(pathOrCode: string): Promise<string>;
  fix(error: string, code?: string): Promise<string>;
  test(path: string, func?: string): Promise<string>;
  review(pathOrCode: string): Promise<string>;
  condense(pathOrText: string, category?: string): Promise<CondenseResult>;

  // Admin
  status(): Promise<MiserStatus>;
  health(): Promise<{ status: string; version: string; model: string }>;
  metrics(): Promise<string>;
}

declare const miser: MiserClient;
export default miser;

export const outline: MiserClient["outline"];
export const grep: MiserClient["grep"];
export const tree: MiserClient["tree"];
export const exists: MiserClient["exists"];
export const read: MiserClient["read"];
export const write: MiserClient["write"];
export const run: MiserClient["run"];
export const ask: MiserClient["ask"];
export const codegen: MiserClient["codegen"];
export const explain: MiserClient["explain"];
export const fix: MiserClient["fix"];
export const test: MiserClient["test"];
export const review: MiserClient["review"];
export const condense: MiserClient["condense"];
export const status: MiserClient["status"];
export const health: MiserClient["health"];
export const metrics: MiserClient["metrics"];
