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

import os
from types import SimpleNamespace

from app.agent import (
    GEMINI_MODEL,
    calculate_financial_exposure,
    check_spanner_hub_inventory,
    execute_spanner_compensating_saga,
    redact_sensitive_erp_payload_after_tool,
    sha256_sliding_window_loop_breaker,
    verify_erp_purchase_order,
)


def test_default_gemini_model_uses_non_retired_ga_endpoint() -> None:
    if "GEMINI_MODEL" not in os.environ:
        assert GEMINI_MODEL == "gemini-3.8-flash"
    assert os.environ.get("GOOGLE_CLOUD_LOCATION") == "global"


def test_verify_erp_purchase_order_contains_3_way_match() -> None:
    res = verify_erp_purchase_order("PO-4500019280")
    assert res["purchase_order_id"] == "PO-4500019280"
    assert res["ordered_qty"] == 1200
    assert res["received_qty_rotterdam"] == 850
    assert res["shortfall_qty"] == 350
    assert res["discrepancy_usd"] == 42000.0
    assert res["three_way_match_status"] == "QTY_SHORTFALL_DETECTED"


def test_check_spanner_hub_inventory() -> None:
    res = check_spanner_hub_inventory("SKU-7740-EU", "EU")
    assert res["frankfurt_hub_available_qty"] == 620
    assert res["frankfurt_safety_stock_floor"] == 200
    assert res["eligible_inter_hub_transfer_qty"] == 420
    assert res["recommended_source_hub"] == "FRANKFURT_HUB_DE02"


def test_calculate_financial_exposure() -> None:
    res = calculate_financial_exposure("PO-4500019280", 350)
    assert res["shortfall_inventory_value_usd"] == 42000.0
    assert res["sla_penalty_at_risk_usd"] == 18500.0
    assert res["total_financial_exposure_usd"] == 60500.0
    assert res["expedited_freight_cost_usd"] == 2450.0
    assert res["net_savings_from_remediation_usd"] == 58050.0


def test_execute_spanner_compensating_saga_commit_and_rollback() -> None:
    committed = execute_spanner_compensating_saga(
        "PO-4500019280", "SKU-7740-EU", 350, simulate_carrier_fault=False
    )
    assert committed["saga_status"] == "ALL_COMMITTED"
    assert len(committed["committed_steps"]) == 3
    assert committed["orphaned_writes"] == 0

    rolled_back = execute_spanner_compensating_saga(
        "PO-4500019280", "SKU-7740-EU", 350, simulate_carrier_fault=True
    )
    assert rolled_back["saga_status"] == "ROLLED_BACK_CLEANLY"
    assert rolled_back["rollback_latency_ms"] == 198
    assert rolled_back["orphaned_writes"] == 0


def test_pre_llm_sdp_redaction_callback() -> None:
    fake_tool = SimpleNamespace(name="verify_erp_purchase_order")
    ctx = SimpleNamespace(state={"rbac_clearance_tier": "STANDARD_ANALYST"})
    raw = verify_erp_purchase_order("PO-99812")
    sanitized = redact_sensitive_erp_payload_after_tool(
        fake_tool, {"purchase_order_id": "PO-99812"}, ctx, raw
    )
    assert sanitized is not None
    assert sanitized["vendor_bank_iban"] == "[REDACTED_BY_GOOGLE_CLOUD_SDP:VENDOR_BANK_IBAN]"
    assert sanitized["swift_routing_code"] == "[REDACTED_BY_GOOGLE_CLOUD_SDP:SWIFT_ROUTING_CODE]"
    assert (
        sanitized["confidential_margin_floor"]
        == "[REDACTED_BY_GOOGLE_CLOUD_SDP:CONFIDENTIAL_MARGIN_FLOOR]"
    )
    assert ctx.state["sdp_redacted_fields_count"] == 3


def test_sha256_sliding_window_loop_breaker_trips_at_k3() -> None:
    fake_tool = SimpleNamespace(name="execute_spanner_compensating_saga")
    ctx = SimpleNamespace(state={})
    args = {"purchase_order_id": "PO-99812", "sku_id": "SKU-7740-EU", "transfer_qty": 350}

    assert sha256_sliding_window_loop_breaker(fake_tool, args, ctx) is None
    assert sha256_sliding_window_loop_breaker(fake_tool, args, ctx) is None
    tripped = sha256_sliding_window_loop_breaker(fake_tool, args, ctx)
    assert tripped is not None
    assert tripped["status"] == "CIRCUIT_BREAKER_TRIPPED"
    assert ctx.state["circuit_breaker_tripped"] is True
