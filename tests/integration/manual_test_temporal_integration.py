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

"""Integration tests for ADK Temporal support."""

import dataclasses
import logging
import uuid
import os
from datetime import timedelta
from typing import AsyncGenerator, List 

import pytest
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter, PydanticPayloadConverter
from temporalio.converter import DataConverter, DefaultPayloadConverter
from temporalio.plugin import SimplePlugin
from temporalio.worker import Worker, WorkflowRunner
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions


from google.genai import types
from google.adk import Agent, Runner, runtime
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.models import LlmRequest, LlmResponse, LLMRegistry
from google.adk.sessions import InMemorySessionService
from google.adk.utils.context_utils import Aclosing
from google.adk.events import Event
from google.adk.integrations.temporal import activity_as_tool, TemporalModel, generate_content_activity

# Required Environment Variables for this test:
# - GOOGLE_CLOUD_PROJECT
# - GOOGLE_CLOUD_LOCATION
# - GOOGLE_GENAI_USE_VERTEXAI (optional, defaults to 1 for this test if needed, or set externally)
# - Temporal Server running at localhost:7233

logger = logging.getLogger(__name__)


@activity.defn
async def get_weather(city: str) -> str:
    """Activity that gets weather."""
    return "Warm and sunny. 17 degrees."

# --- Customized LLM Activities for Better Trace Visibility ---

@activity.defn(name="coordinator_think")
async def coordinator_think(req: LlmRequest) -> List[LlmResponse]:
    """Activity for the Coordinator agent."""
    return await generate_content_activity(req)

@activity.defn(name="tool_agent_think")
async def tool_agent_think(req: LlmRequest) -> List[LlmResponse]:
    """Activity for the Tool Agent."""
    return await generate_content_activity(req)

@activity.defn(name="specialist_think")
async def specialist_think(req: LlmRequest) -> List[LlmResponse]:
    """Activity for the Specialist/Handoff Agent."""
    return await generate_content_activity(req)


@workflow.defn
class WeatherAgent:
    @workflow.run
    async def run(self, prompt: str) -> Event | None:
        logger.info("Workflow started.")
        
        # 1. Configure ADK Runtime to use Temporal Determinism
        runtime.set_time_provider(lambda: workflow.now().timestamp())
        runtime.set_id_provider(lambda: str(workflow.uuid4()))

        # 2. Define Agent using Temporal Helpers
        # Uses generic 'generate_content_activity' by default
        agent_model = TemporalModel(
            model_name="gemini-2.5-pro",
            start_to_close_timeout=timedelta(minutes=2)
        )
        
        # Wraps 'get_weather' activity as a Tool
        weather_tool = activity_as_tool(
            get_weather,
            start_to_close_timeout=timedelta(seconds=60)
        )

        agent = Agent(
            name='test_agent',
            model=agent_model,
            tools=[weather_tool]
        )

        # 3. Create Session (uses runtime.new_uuid() -> workflow.uuid4())
        session_service = InMemorySessionService()
        logger.info("Create session.")
        session = await session_service.create_session(app_name="test_app", user_id="test")
        
        logger.info(f"Session created with ID: {session.id}")

        # 4. Run Agent
        runner = Runner(
            agent=agent,
            app_name='test_app',
            session_service=session_service,
        )

        logger.info("Starting runner.")
        last_event = None
        async with Aclosing(runner.run_async(
            user_id="test",
            session_id=session.id,
            new_message=types.Content(
                role='user', parts=[types.Part(text=prompt)]
            ),
        )) as agen:
            async for event in agen:
                logger.info(f"Event: {event}")
                last_event = event
        
        return last_event

@workflow.defn
class MultiAgentWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        # 1. Runtime Setup
        runtime.set_time_provider(lambda: workflow.now().timestamp())
        runtime.set_id_provider(lambda: str(workflow.uuid4()))

        # 2. Define Distinct Models for Visualization
        # We use a separate activity for each agent so they show up distinctly in the Temporal UI.
        
        coordinator_model = TemporalModel(
            model_name="gemini-2.5-pro",
            activity_def=coordinator_think,
            start_to_close_timeout=timedelta(minutes=2)
        )

        tool_agent_model = TemporalModel(
            model_name="gemini-2.5-pro",
            activity_def=tool_agent_think,
            start_to_close_timeout=timedelta(minutes=2)
        )

        specialist_model = TemporalModel(
            model_name="gemini-2.5-pro",
            activity_def=specialist_think,
            start_to_close_timeout=timedelta(minutes=2)
        )

        # 3. Define Sub-Agents
        
        # Agent to be used as a Tool
        tool_agent = LlmAgent(
            name="ToolAgent",
            model=tool_agent_model,
            instruction="You are a tool agent. You help with specific sub-tasks. Always include 'From ToolAgent:' in your response."
        )
        agent_tool = AgentTool(tool_agent)

        # Agent to be transferred to (Handoff)
        handoff_agent = LlmAgent(
            name="HandoffAgent",
            model=specialist_model,
            instruction="You are a Specialist Agent. You handle specialized requests. Always include 'From HandoffAgent:' in your response."
        )

        # 4. Define Parent Agent
        parent_agent = LlmAgent(
            name="Coordinator",
            model=coordinator_model,
            # Instructions to guide the LLM when to use which
            instruction=(
                "You are a Coordinator. "
                "CRITICAL INSTRUCTION: You MUST NOT answer user queries directly if they related to specific tasks. "
                "1. If the user asks for 'help' or 'subtask', you MUST use the 'ToolAgent' tool (AgentTool). "
                "2. If the user asks to 'switch' or 'specialist', you MUST transfer to the HandoffAgent using 'transfer_to_agent'. "
                "Do not apologize. Do not say you will do it. Just call the function."
            ),
            tools=[agent_tool],
            sub_agents=[handoff_agent]
        )

        # 5. Execute
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="multi_agent_app", user_id="user_MULTI")
        
        runner = Runner(
            agent=parent_agent,
            app_name='multi_agent_app',
            session_service=session_service,
        )

        # We will run a multi-turn conversation to test both paths
        # Turn 1: Trigger Tool
        logger.info("--- Turn 1: Trigger Tool ---")
        tool_response_text = ""
        async with Aclosing(runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=types.Content(role='user', parts=[types.Part(text="I need help with a subtask.")])
        )) as agen:
            async for event in agen:
                logger.info(f"Event Author: {event.author} | Actions: {event.actions}")
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text: tool_response_text += part.text

        # Turn 2: Trigger Handoff
        logger.info("--- Turn 2: Trigger Handoff ---")
        handoff_response_text = ""
        async with Aclosing(runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=types.Content(role='user', parts=[types.Part(text="Please switch me to the specialist.")])
        )) as agen:
            async for event in agen:
                logger.info(f"Event Author: {event.author} | Actions: {event.actions}")
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text: handoff_response_text += part.text

        logger.info(f"Tool Response: {tool_response_text}")
        logger.info(f"Handoff Response: {handoff_response_text}")
        
        return f"Tool: {tool_response_text} | Handoff: {handoff_response_text}"


class ADKPlugin(SimplePlugin):
    def __init__(self):
        super().__init__(
            name="ADKPlugin",
            data_converter=_data_converter,
            workflow_runner=workflow_runner,
        )

def workflow_runner(runner: WorkflowRunner | None) -> WorkflowRunner:
    if not runner:
        raise ValueError("No WorkflowRunner provided to the ADK plugin.")

    # If in sandbox, add additional passthrough
    if isinstance(runner, SandboxedWorkflowRunner):
        return dataclasses.replace(
            runner,
            restrictions=runner.restrictions.with_passthrough_modules("google.adk", "google.genai"),
        )
    return runner

def _data_converter(converter: DataConverter | None) -> DataConverter:
    if converter is None:
        return pydantic_data_converter
    elif converter.payload_converter_class is DefaultPayloadConverter:
        return dataclasses.replace(
            converter, payload_converter_class=PydanticPayloadConverter
        )
    elif not isinstance(converter.payload_converter, PydanticPayloadConverter):
        raise ValueError(
            "The payload converter must be of type PydanticPayloadConverter."
        )
    return converter

@pytest.mark.asyncio
async def test_temporalio_integration():
    """Run full integration test with Temporal Server."""
    
    # Normally this should only run if local Temporal server is available
    # For now, we assume it is, as per user context.
    
    # Start client/worker
    if "GOOGLE_CLOUD_PROJECT" not in os.environ:
        pytest.skip("GOOGLE_CLOUD_PROJECT not set. Skipping integration test.")

    try:
        client = await Client.connect("localhost:7233", plugins=[ADKPlugin()])
    except RuntimeError:
        pytest.skip("Could not connect to Temporal server. Is it running?")

    async with Worker(
        client,
        workflows=[WeatherAgent, MultiAgentWorkflow],
        activities=TemporalModel.default_activities() + [
            get_weather, 
            coordinator_think, 
            tool_agent_think, 
            specialist_think
        ],
        task_queue="hello_world_queue",
        max_cached_workflows=0,
    ) as worker:
        print("Worker started.")
        # Run Weather Agent
        result_weather = await client.execute_workflow(
            WeatherAgent.run,
            "What is the weather in Tokyo?",
            id=str(uuid.uuid4()),
            task_queue="hello_world_queue",
        )
        print(f"Weather Agent Result: {result_weather}")

        # Run Multi-Agent Workflow
        result_multi = await client.execute_workflow(
            MultiAgentWorkflow.run,
            "start", # Argument ignored in run logic (hardcoded prompts)
            id=str(uuid.uuid4()),
            task_queue="hello_world_queue",
        )
        print(f"Multi-Agent Result: {result_multi}")
