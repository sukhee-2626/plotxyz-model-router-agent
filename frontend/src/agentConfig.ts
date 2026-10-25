export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = {
  "slug": "plotxyz-model-router-agent",
  "title": "Model Router",
  "tagline": "Pick the right model for the job, not the loudest one.",
  "purpose": "Ranks configured models using capability, latency, and cost weights, with optional latency and cost ceilings.",
  "accent": "#818cf8",
  "features": [
    "Weighted capability/latency/cost scoring",
    "Hard constraint filtering",
    "Explainable routing table"
  ],
  "limitations": [
    "Cost and latency values are user-supplied and may be stale.",
    "The agent does not call the models it ranks."
  ],
  "fields": [
    {
      "name": "models",
      "label": "Model catalog (JSON)",
      "type": "textarea",
      "rows": 7,
      "placeholder": ""
    },
    {
      "name": "task",
      "label": "Task (coding, chat, cheap, balanced)",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "max_latency_ms",
      "label": "Max latency (ms)",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "max_cost_per_1k",
      "label": "Max cost per 1k",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "models": "[{\"name\":\"fast-local\",\"capability\":62,\"latency_ms\":180,\"cost_per_1k\":0},{\"name\":\"balanced-local\",\"capability\":78,\"latency_ms\":420,\"cost_per_1k\":0.2},{\"name\":\"quality-cloud\",\"capability\":92,\"latency_ms\":900,\"cost_per_1k\":1.8}]",
    "task": "coding",
    "max_latency_ms": 1200,
    "max_cost_per_1k": 2
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-model-router-agent"
};
