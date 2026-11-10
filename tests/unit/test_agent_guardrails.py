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

from app.agent import (
    calculate_financial_exposure,
    check_spanner_hub_inventory,
    execute_spanner_compensating_saga,
    verify_erp_purchase_order,
)


def test_verify_erp_purchase_order_contains_3_way_match() -> None:
    res = verify_erp_purchase_order("PO-4500019280")
    assert res["purchase_order_id"] == "PO-4500019280"
    assert res["shortfall_qty"] == 350
    assert res["three_way_match_status"] == "QTY_SHORTFALL_DETECTED"


def test_check_spanner_hub_inventory() -> None:
    res = check_spanner_hub_inventory("SKU-7740-EU", "EU")
    assert res["eligible_inter_hub_transfer_qty"] == 420
    assert res["recommended_source_hub"] == "FRANKFURT_HUB_DE02"


def test_calculate_financial_exposure() -> None:
    res = calculate_financial_exposure("PO-4500019280", 350)
    assert res["total_financial_exposure_usd"] == 60500.0
    assert res["net_savings_from_remediation_usd"] == 58050.0


def test_execute_spanner_compensating_saga_commit_and_rollback() -> None:
    committed = execute_spanner_compensating_saga(
        "PO-4500019280", "SKU-7740-EU", 350, simulate_carrier_fault=False
    )
    assert committed["saga_status"] == "ALL_COMMITTED"
    assert len(committed["committed_steps"]) == 3

    rolled_back = execute_spanner_compensating_saga(
        "PO-4500019280", "SKU-7740-EU", 350, simulate_carrier_fault=True
    )
    assert rolled_back["saga_status"] == "ROLLED_BACK_CLEANLY"
    assert rolled_back["orphaned_writes"] == 0
