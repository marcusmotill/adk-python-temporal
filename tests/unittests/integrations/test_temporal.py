# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for Temporal integration helpers."""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import asyncio
from typing import Any

from google.genai import types

# Configure Mocks globally
# We create fresh mocks here.
mock_workflow = MagicMock()
mock_activity = MagicMock()
mock_worker = MagicMock()
mock_client = MagicMock()

# Important: execute_activity must be awaitable
mock_workflow.execute_activity = AsyncMock(return_value="mock_result")

# Mock the parent package
mock_temporalio = MagicMock()
mock_temporalio.workflow = mock_workflow
mock_temporalio.activity = mock_activity
mock_temporalio.worker = mock_worker
mock_temporalio.client = mock_client

# Mock sys.modules
with patch.dict(sys.modules, {
    "temporalio": mock_temporalio,
    "temporalio.workflow": mock_workflow,
    "temporalio.activity": mock_activity,
    "temporalio.worker": mock_worker,
    "temporalio.client": mock_client,
}):
    from google.adk.integrations import temporal
    from google.adk.models import LlmRequest, LlmResponse


class TestTemporalIntegration(unittest.TestCase):

    def test_activity_as_tool_wrapper(self):
        # Reset mocks
        mock_workflow.reset_mock()
        mock_workflow.execute_activity = AsyncMock(return_value="mock_result")
        
        # Verify mock setup
        # If this fails, then 'temporal.workflow' is NOT our 'mock_workflow'
        assert temporal.workflow.execute_activity is mock_workflow.execute_activity

        # Define a fake activity
        async def fake_activity(arg: str) -> str:
            """My Docstring."""
            return f"Hello {arg}"
        
        fake_activity.name = "fake_activity_name"

        # Create tool
        tool = temporal.activity_as_tool(
            fake_activity,
            start_to_close_timeout=100
        )

        # Check metadata
        self.assertEqual(tool.__name__, "fake_activity_name")
        self.assertEqual(tool.__doc__, "My Docstring.")

        # Run tool (wrapper)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(tool("World"))
        finally:
            loop.close()

        # Verify call
        mock_workflow.execute_activity.assert_called_once()
        args, kwargs = mock_workflow.execute_activity.call_args
        self.assertEqual(kwargs['args'], ['World'])
        self.assertEqual(kwargs['start_to_close_timeout'], 100)

    def test_temporal_model_generate_content(self):
        # Reset mocks
        mock_workflow.reset_mock()
        
        # Prepare valid LlmResponse with content
        response_content = types.Content(parts=[types.Part(text="test_resp")])
        llm_response = LlmResponse(content=response_content)
        
        # generate_content_async expects execute_activity to return response list (iterator)
        mock_workflow.execute_activity = AsyncMock(return_value=[llm_response])
        
        # Mock an activity def
        mock_activity_def = MagicMock()
        
        # Create model
        model = temporal.TemporalModel(
            model_name="test-model",
            activity_def=mock_activity_def,
            schedule_to_close_timeout=50
        )

        # Create request
        req = LlmRequest(model="test-model", prompt="hi")
        
        # Run generate_content_async (it is an async generator)
        async def run_gen():
            results = []
            async for r in model.generate_content_async(req):
                results.append(r)
            return results

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            results = loop.run_until_complete(run_gen())
        finally:
            loop.close()

        # Verify execute_activity called
        mock_workflow.execute_activity.assert_called_once()
        args, kwargs = mock_workflow.execute_activity.call_args
        self.assertEqual(kwargs['args'], [req])
        self.assertEqual(kwargs['schedule_to_close_timeout'], 50)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].content.parts[0].text, "test_resp")

