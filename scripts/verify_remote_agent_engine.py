#!/usr/bin/env python3
"""Verify live remote execution against a deployed Agent Engine instance on Gemini Enterprise Agent Platform."""

import asyncio
import json
import os

import vertexai


async def main() -> None:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    reasoning_engine_id = os.environ.get(
        "REASONING_ENGINE_RESOURCE_NAME",
        "projects/551887XXXXXX/locations/us-central1/reasoningEngines/366446609694720000",
    )

    client = vertexai.Client(project=project_id, location=location)
    remote_agent = client.agent_engines.get(name=reasoning_engine_id)
    print(f"Connected to Remote Agent Engine: {remote_agent.api_resource.name}")
    print(f"Display Name: {remote_agent.api_resource.display_name}")

    session = await remote_agent.async_create_session(user_id="cloud-sre-auditor")
    session_id = (
        session["id"] if isinstance(session, dict) else getattr(session, "id", None)
    )
    print(f"Created Remote Session ID: {session_id}")

    prompt = (
        "Audit Purchase Order PO-99812 for SKU-7740-EU, check EU hub inventory "
        "in Cloud Spanner, calculate financial exposure in BigQuery, and execute "
        "the remediation saga, returning the complete Order-to-Cash Audit Receipt."
    )
    events = []
    async for event in remote_agent.async_stream_query(
        user_id="cloud-sre-auditor",
        session_id=session_id,
        message=prompt,
    ):
        events.append(event)
        print("REMOTE EVENT:", json.dumps(event)[:300])

    print(f"Total Remote Events Received: {len(events)}")


if __name__ == "__main__":
    asyncio.run(main())
