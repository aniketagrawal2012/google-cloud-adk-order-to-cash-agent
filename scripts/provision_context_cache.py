#!/usr/bin/env python3
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
"""Provision an Explicit Gemini Platform Context Cache for static Order-to-Cash SOP & MCP schemas."""

import os
from pathlib import Path

from google import genai
from google.genai import types


def build_static_o2c_corpus() -> str:
    """Builds the prefix-invariant Order-to-Cash SOP & schema corpus for explicit caching."""
    spec_path = Path(__file__).resolve().parent.parent / ".agents-cli-spec.md"
    base_spec = (
        spec_path.read_text(encoding="utf-8")
        if spec_path.exists()
        else "Enterprise Order-to-Cash & Supply-Chain Governance Specification"
    )
    incoterms_clauses = "\n".join(
        f"CLAUSE-INCOTERMS-2026-{i:03d}: DDP Rotterdam/Frankfurt 48h SLA penalty=$18,500; "
        f"Frankfurt Hub safety stock floor=200 units; max scoped A2A freight delegation=$50,000 (TTL=5s)."
        for i in range(1, 180)
    )
    return f"{base_spec}\n\n## Canonical Incoterms 2026 & ERP Schema Reference\n{incoterms_clauses}\n"


def create_enterprise_o2c_context_cache(
    project_id: str | None = None,
    location: str | None = None,
    model: str | None = None,
    ttl: str = "3600s",
) -> str:
    """Pins the static Order-to-Cash prefix into Gemini Enterprise Agent Platform Explicit Context Caching."""
    resolved_project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
    resolved_location = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    resolved_model = model or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(vertexai=True, project=resolved_project, location=resolved_location)

    cache = client.caches.create(
        model=resolved_model,
        config=types.CreateCachedContentConfig(
            display_name="o2c_enterprise_erp_schema_v2_2",
            system_instruction=(
                "You are the Enterprise Order-to-Cash & Supply-Chain Governance Agent on Google Cloud. "
                "Enforce pre-LLM Sensitive Data Protection and Cloud Spanner compensating saga idempotency."
            ),
            contents=[build_static_o2c_corpus()],
            ttl=ttl,
        ),
    )
    print(f"Provisioned Gemini Platform Explicit Context Cache: {cache.name}")
    return str(cache.name)


if __name__ == "__main__":
    create_enterprise_o2c_context_cache()
