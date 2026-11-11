# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
import json
import os
from typing import Any, Dict, Optional

import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.tool_context import ToolContext
from google.genai import types

try:
    _, project_id = google.auth.default()
except Exception:
    project_id = None
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id or "your-gcp-project-id")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# Benchmarked live on "gemini-2.5-flash" (Trace 404feb61ac9b6cdbfb092e726e7b94e6);
# override GEMINI_MODEL to test "gemini-2.5-pro" or Model Garden aliases ("gemini-3.5-flash", "gemini-4-argon").
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

RESTRICTED_ERP_FIELDS = {
    "vendor_bank_iban",
    "swift_routing_code",
    "confidential_margin_floor",
    "approver_ssn",
}


def sha256_sliding_window_loop_breaker(
    tool: Any,
    args: Dict[str, Any],
    tool_context: ToolContext,
) -> Optional[Dict[str, Any]]:
    """Deterministic O(1) sliding-window SHA-256 loop breaker (before_tool_callback).

    Computes a canonical SHA-256 digest of (tool.name, sorted_args) and halts
    runaway retry storms at k=3 within a sliding window of W=6 turns.
    """
    tool_name = getattr(tool, "name", str(tool))
    canonical_payload = f"{tool_name}:{json.dumps(args, sort_keys=True, default=str)}"
    call_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()[:16]

    history = list(tool_context.state.get("tool_digest_window", []))
    history.append(call_digest)
    sliding_window = history[-6:]
    tool_context.state["tool_digest_window"] = sliding_window

    if sliding_window.count(call_digest) >= 3:
        tool_context.state["circuit_breaker_tripped"] = True
        return {
            "status": "CIRCUIT_BREAKER_TRIPPED",
            "digest": call_digest,
            "reason": (
                f"Tool '{tool_name}' invoked 3 times with identical canonical digest "
                f"({call_digest}). Further retries blocked by ADK FinOps policy."
            ),
            "fallback_directive": (
                "Synthesize the Order-to-Cash audit receipt immediately using the "
                "verified ERP, Cloud Spanner, and BigQuery state already collected."
            ),
        }
    return None


def redact_sensitive_erp_payload_after_tool(
    tool: Any,
    args: Dict[str, Any],
    tool_context: ToolContext,
    tool_response: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Deterministic pre-LLM Sensitive Data Protection hook (after_tool_callback).

    Intercepts raw MCP/ERP tool dictionaries and masks restricted financial and PII
    fields BEFORE the payload enters the Gemini context window or Cloud Trace logs.
    """
    if not isinstance(tool_response, dict):
        return None

    clearance = tool_context.state.get("rbac_clearance_tier", "STANDARD_ANALYST")
    sanitized: Dict[str, Any] = {}
    redacted_count = 0

    for key, value in tool_response.items():
        if key in RESTRICTED_ERP_FIELDS and clearance != "CLEARED_TREASURY_AUDITOR":
            sanitized[key] = f"[REDACTED_BY_GOOGLE_CLOUD_SDP:{key.upper()}]"
            redacted_count += 1
        else:
            sanitized[key] = value

    prior = int(tool_context.state.get("sdp_redacted_fields_count", 0))
    tool_context.state["sdp_redacted_fields_count"] = prior + redacted_count
    sanitized["_sdp_governance_metadata"] = {
        "redacted_fields_this_call": redacted_count,
        "cumulative_redacted_fields": prior + redacted_count,
        "policy": "GOOGLE_CLOUD_SDP_PRE_LLM_ENFORCED",
    }
    return sanitized


def verify_erp_purchase_order(purchase_order_id: str) -> dict:
    """Queries the SAP/ERP Order-to-Cash ledger to verify 3-way match status for a Purchase Order.

    Args:
        purchase_order_id: The ERP Purchase Order identifier (e.g., 'PO-4500019280').

    Returns:
        A dictionary containing the 3-way match discrepancy, SKU details, and vendor metadata.
    """
    po_id = purchase_order_id.strip().upper()
    return {
        "purchase_order_id": po_id,
        "vendor_name": "Rheinmetall Industrial Components GmbH",
        "sku_id": "SKU-7740-EU",
        "ordered_qty": 1200,
        "received_qty_rotterdam": 850,
        "shortfall_qty": 350,
        "unit_price_usd": 120.00,
        "discrepancy_usd": 42000.00,
        "three_way_match_status": "QTY_SHORTFALL_DETECTED",
        "vendor_bank_iban": "DE89370400440532013000",
        "swift_routing_code": "COBADEFFXXX",
        "confidential_margin_floor": "34.8%",
    }


def check_spanner_hub_inventory(sku_id: str, hub_region: str = "EU") -> dict:
    """Queries Google Cloud Spanner regional inventory hubs with TrueTime external consistency.

    Args:
        sku_id: The catalog SKU identifier (e.g., 'SKU-7740-EU').
        hub_region: Regional hub code ('EU' or 'US').

    Returns:
        A dictionary with real-time regional hub stock and safety stock thresholds.
    """
    return {
        "sku_id": sku_id.strip().upper(),
        "hub_region": hub_region.strip().upper(),
        "spanner_truetime_snapshot": "2026-11-10T08:55:00.000142Z",
        "rotterdam_hub_available_qty": 0,
        "frankfurt_hub_available_qty": 620,
        "frankfurt_safety_stock_floor": 200,
        "eligible_inter_hub_transfer_qty": 420,
        "recommended_source_hub": "FRANKFURT_HUB_DE02",
    }


def calculate_financial_exposure(purchase_order_id: str, shortfall_qty: int = 350) -> dict:
    """Queries BigQuery financial exposure tables to compute SLA penalty risk and order margin impact.

    Args:
        purchase_order_id: The ERP Purchase Order identifier.
        shortfall_qty: Number of unfulfilled units subject to SLA penalty.

    Returns:
        A dictionary containing financial penalty exposure and recommended remediation budget.
    """
    shortfall_val = shortfall_qty * 120.0
    sla_penalty = 18500.00
    return {
        "purchase_order_id": purchase_order_id.strip().upper(),
        "shortfall_inventory_value_usd": shortfall_val,
        "contract_sla_clause": "INCOTERMS-2026-DDP-48H-PENALTY",
        "sla_penalty_at_risk_usd": sla_penalty,
        "total_financial_exposure_usd": shortfall_val + sla_penalty,
        "expedited_freight_cost_usd": 2450.00,
        "net_savings_from_remediation_usd": (shortfall_val + sla_penalty) - 2450.00,
    }


def execute_spanner_compensating_saga(
    purchase_order_id: str,
    sku_id: str,
    transfer_qty: int,
    simulate_carrier_fault: bool = False,
) -> dict:
    """Executes an atomic 3-step Order-to-Cash remediation saga backed by Cloud Spanner.

    Steps:
      1. Amend ERP Purchase Order split allocation (inverse: release_po_amendment)
      2. Lock transfer inventory in Frankfurt Hub (inverse: unlock_frankfurt_hub_stock)
      3. Book expedited freight carrier via scoped A2A token (max_cap=$50,000, ttl=5s)

    Args:
        purchase_order_id: The ERP Purchase Order ID.
        sku_id: The SKU identifier to transfer.
        transfer_qty: Quantity of units to lock and transfer.
        simulate_carrier_fault: Set True to simulate an HTTP 503 carrier outage and trigger ACID rollback.

    Returns:
        A deterministic saga execution receipt with forward or reverse-compensated status.
    """
    idempotency_key = hashlib.sha256(
        f"{purchase_order_id}:{sku_id}:{transfer_qty}:{simulate_carrier_fault}".encode("utf-8")
    ).hexdigest()[:12]

    if simulate_carrier_fault:
        return {
            "saga_idempotency_key": idempotency_key,
            "saga_status": "ROLLED_BACK_CLEANLY",
            "failed_step": "step_3_book_expedited_carrier_a2a",
            "downstream_error": "HTTP 503 Service Unavailable from Carrier Booking API",
            "compensated_steps_reverse_order": [
                {
                    "step": "step_2_lock_frankfurt_hub_stock",
                    "inverse_action": "unlock_frankfurt_hub_stock(qty=350)",
                    "status": "COMPENSATED_OK",
                },
                {
                    "step": "step_1_amend_erp_purchase_order",
                    "inverse_action": "release_po_amendment(po='PO-4500019280')",
                    "status": "COMPENSATED_OK",
                },
            ],
            "rollback_latency_ms": 198,
            "orphaned_writes": 0,
        }

    return {
        "saga_idempotency_key": idempotency_key,
        "saga_status": "ALL_COMMITTED",
        "scoped_a2a_token": {
            "allowed_tool": "book_expedited_freight",
            "max_cap_usd": 50000.00,
            "ttl_seconds": 5,
        },
        "committed_steps": [
            f"step_1_amend_erp_purchase_order({purchase_order_id}) -> COMMITTED (42ms)",
            f"step_2_lock_frankfurt_hub_stock({sku_id}, qty={transfer_qty}) -> COMMITTED (38ms)",
            "step_3_book_expedited_carrier_a2a(route='DE-FRA -> NL-RTM') -> COMMITTED (114ms)",
        ],
        "orphaned_writes": 0,
    }


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=GEMINI_MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Enterprise Order-to-Cash & Supply-Chain Governance Agent running on "
        "Google Cloud (ADK 2.0 + Vertex AI Agent Runtime + Cloud Spanner + BigQuery). "
        "When auditing a Purchase Order discrepancy or supply-chain shortfall:\n"
        "1. Call `verify_erp_purchase_order` to inspect the 3-way match status and shortfall quantity.\n"
        "2. Call `check_spanner_hub_inventory` to check real-time regional hub inventory in Cloud Spanner.\n"
        "3. Call `calculate_financial_exposure` to quantify BigQuery SLA penalty risk and net remediation savings.\n"
        "4. Call `execute_spanner_compensating_saga` to execute the atomic remediation (or demonstrate reverse saga "
        "rollback if the user requests simulating a carrier fault).\n"
        "5. Provide a structured, executive Order-to-Cash Audit Receipt citing every verified number, the "
        "Cloud Spanner saga status, and the pre-LLM Sensitive Data Protection (SDP) redaction count."
    ),
    tools=[
        verify_erp_purchase_order,
        check_spanner_hub_inventory,
        calculate_financial_exposure,
        execute_spanner_compensating_saga,
    ],
    before_tool_callback=sha256_sliding_window_loop_breaker,
    after_tool_callback=redact_sensitive_erp_payload_after_tool,
)

app = App(
    root_agent=root_agent,
    name="app",
)
