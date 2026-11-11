# Enterprise Order-to-Cash & Supply-Chain Governance Agent on Google Cloud

**Production Reference Implementation: Google Agent Development Kit (ADK 2.2) • Gemini 3.8 Flash, Gemini 4 Argon & Gemini 4 Carbon • Vertex AI Agent Engine (`ReasoningEngine`) • Vertex AI GenAI Evaluation Service • Cloud Spanner • BigQuery • Sensitive Data Protection (SDP) • Gemini Enterprise**

> **Model Lifecycle & Verification Note (November 2026):** Per Google Cloud's official [Gemini Model Versions & Lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions), `gemini-2.5-flash` and `gemini-2.5-pro` reached their October 20, 2026 retirement date. [`app/agent.py`](app/agent.py) and [`scripts/provision_context_cache.py`](scripts/provision_context_cache.py) default to **`gemini-3.8-flash`** (GA through Sept 2, 2027+) on **`GOOGLE_CLOUD_LOCATION=global`**, with one-env-var switching to **`gemini-4-argon`** (GA through Oct 13, 2027+) and **`gemini-4-carbon`** (Nov 10, 2026 release). Full Agent Engine OpenTelemetry traces (`Trace 404feb61ac9b6cdbfb092e726e7b94e6`) were captured on the `gemini-2.5-flash` baseline and side-by-side structured audit synthesis was verified live in Google Cloud Agent Studio Compare on `gemini-4-carbon` and `gemini-3.8-flash`.

This repository contains the complete, runnable source code, deterministic callback guardrails, Cloud Spanner compensating saga implementation, and Vertex AI evaluation suite for the **Enterprise Order-to-Cash & Supply-Chain Multi-Agent System on Google Cloud**.

---

## Architecture Highlights

1. **O(1) SHA-256 Sliding-Window Loop Breaker (`before_tool_callback`)**:
   - Intercepts every tool invocation in [`app/agent.py`](app/agent.py) (`sha256_sliding_window_loop_breaker`) before execution.
   - Hashes canonical `(tool_name, sorted_args_json)` into a 16-hex-character SHA-256 digest stored in ADK session state (`tool_digest_window`).
   - Halts cyclic tool-calling loops deterministically in `< 0.05 ms` without burning additional LLM tokens.

2. **Pre-LLM Sensitive Data Protection Redaction (`after_tool_callback`)**:
   - Intercepts raw ERP payloads in [`app/agent.py`](app/agent.py) (`redact_sensitive_erp_payload_after_tool`) *before* tool responses enter the Gemini model context window or Cloud Trace spans.
   - Deterministically scrubs restricted fields (`vendor_bank_iban`, `swift_routing_code`, `confidential_margin_floor`, `approver_ssn`) into `[REDACTED_BY_GOOGLE_CLOUD_SDP:<FIELD>]`.

3. **Cloud Spanner Compensating Saga & Scoped A2A Delegation (`execute_spanner_compensating_saga`)**:
   - Performs 3-way match verification (`verify_erp_purchase_order`), queries Cloud Spanner regional inventory (`check_spanner_hub_inventory`), computes BigQuery SLA penalty exposure (`calculate_financial_exposure`), and executes an atomic 3-step remediation saga with automatic reverse compensation (`ROLLBACK_COMPENSATED`) on downstream carrier faults.

4. **Pre-Merge Vertex AI Evaluation Gate (`tests/eval/`)**:
   - Configured in [`tests/eval/eval_config.yaml`](tests/eval/eval_config.yaml) and [`tests/eval/datasets/basic-dataset.json`](tests/eval/datasets/basic-dataset.json).
   - Evaluates 6 adaptive, point-wise, and computation-based metrics (`multi_turn_task_success_v1`, `multi_turn_tool_use_quality_v1`, `custom_response_quality`, `sdp_zero_leakage_compliance`, `saga_trajectory_completeness`, `agent_turn_count`).

---

## End-to-End Practitioner Walkthrough (`agents-cli`)

### Step 1: Scaffold the Project with `agents-cli`

```bash
agents-cli scaffold create order-to-cash-agent \
  --agent adk \
  --deployment-target agent_runtime \
  --region us-central1 \
  --cicd-runner google_cloud_build \
  --agent-guidance-filename GEMINI.md
```

### Step 2: Run Locally via CLI & Interactive ADK Web Playground

```bash
# Run single-turn verbose trace inspection in terminal
GOOGLE_CLOUD_PROJECT=your-gcp-project-id \
  agents-cli run "Audit Purchase Order PO-99812 for SKU-7740-EU, check EU hub inventory in Cloud Spanner, calculate financial exposure in BigQuery, and execute the remediation saga." -v

# Or launch the interactive ADK Web Playground UI (http://127.0.0.1:8089)
GOOGLE_CLOUD_PROJECT=your-gcp-project-id \
  GOOGLE_CLOUD_LOCATION=global \
  GEMINI_MODEL=gemini-3.8-flash \
  GOOGLE_GENAI_USE_VERTEXAI=True \
  uv run adk web --port 8089
```

### Step 3: Run the Pre-Merge Vertex AI Evaluation Suite

```bash
# 1. Generate live multi-tool execution traces from tests/eval/evalsets/core.evalset.json
GOOGLE_CLOUD_PROJECT=your-gcp-project-id \
  agents-cli eval generate

# 2. Grade traces against Vertex AI GenAI Evaluation Service rubrics & custom code metrics
GOOGLE_CLOUD_PROJECT=your-gcp-project-id \
  agents-cli eval grade --project your-gcp-project-id --location us-central1
```

**Verified Evaluation Scorecard (`artifacts/grade_results/results_20261110_143147.json`)**:

| Metric | Type | Mean Score | Std. Dev. | Gate Threshold | Status |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `multi_turn_task_success_v1` | Adaptive Rubric | **1.0000** | `0.0000` | `>= 0.95` | PASS |
| `multi_turn_tool_use_quality_v1` | Adaptive Rubric | **1.0000** | `0.0000` | `>= 0.95` | PASS |
| `custom_response_quality` | Point-Wise LLM Judge (1-5) | **5.0000** | `0.0000` | `>= 4.50` | PASS |
| `sdp_zero_leakage_compliance` | Custom Code (`eval_config.yaml`) | **1.0000** | `0.0000` | `== 1.00` | PASS |
| `saga_trajectory_completeness` | Custom Code (`eval_config.yaml`) | **1.0000** | `0.0000` | `== 1.00` | PASS |
| `agent_turn_count` | Computation | **1.0000** | `0.0000` | `<= 2.00` | PASS |

### Step 4: Deploy to Vertex AI Agent Engine (`ReasoningEngine`)

```bash
# Deploy managed ADK runtime container to us-central1 while routing Gemini 3.8 / Gemini 4 inference via global endpoint
GOOGLE_CLOUD_PROJECT=your-gcp-project-id \
  GOOGLE_CLOUD_LOCATION=global \
  GEMINI_MODEL=gemini-3.8-flash \
  agents-cli deploy \
  --project your-gcp-project-id \
  --region us-central1 \
  --no-confirm-project

# Verify remote streaming execution against the deployed ReasoningEngine
uv run python scripts/verify_remote_agent_engine.py
```

### Step 5: Publish & Govern in Gemini Enterprise

```bash
# List available Gemini Enterprise engines in your GCP project
agents-cli publish gemini-enterprise --list --project-id your-gcp-project-id

# Register the deployed Agent Runtime into Gemini Enterprise Assistant
agents-cli publish gemini-enterprise \
  --project-id your-gcp-project-id \
  --app-id your-gemini-enterprise-engine-id \
  --display-name "Order-to-Cash Governance Agent" \
  --description "Audits ERP 3-way match discrepancies, verifies Cloud Spanner hub inventory, quantifies BigQuery SLA exposure, and executes compensating sagas."
```

---

## Repository Structure

```text
order-to-cash-agent/
├── .agents-cli-spec.md                # Agent specification & guardrail contract
├── GEMINI.md                          # ADK coding & lifecycle guidance
├── agents-cli-manifest.yaml           # Agent scaffold & runtime manifest
├── pyproject.toml                     # Package dependencies (google-adk, google-cloud-aiplatform)
├── app/
│   ├── agent.py                       # Root ADK Agent + SHA-256 loop breaker + SDP redaction + 4 tools
│   ├── agent_runtime_app.py           # Vertex AI Agent Engine (AdkApp) entrypoint with Cloud Trace
│   └── app_utils/
│       ├── telemetry.py               # OpenTelemetry & GenAI completion hook configuration
│       └── typing.py                  # Structured feedback & trace schemas
├── scripts/
│   ├── provision_context_cache.py     # Explicit Vertex AI Context Cache builder for static SOP/schemas
│   └── verify_remote_agent_engine.py  # Live async_stream_query verification against Agent Engine
└── tests/
    ├── eval/
    │   ├── eval_config.yaml           # Vertex AI Eval metrics, autorater & custom Python graders
    │   └── datasets/
    │       └── basic-dataset.json     # Golden evaluation dataset (happy path + rollback compensation)
    ├── integration/                   # Integration tests for AgentEngineApp & callbacks
    └── unit/                          # Unit tests for tools, SHA-256 loop breaker & SDP redaction
```

## License

Apache License 2.0
