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

"""Temporal integration helpers for ADK."""

import functools
from typing import Any, AsyncGenerator, Callable, Optional, List

from temporalio import workflow, activity
from google.adk.models import BaseLlm, LlmRequest, LlmResponse, LLMRegistry
from google.genai import types


def activity_as_tool(
    activity_def: Callable,
    **activity_options: Any
) -> Callable:
    """Wraps a Temporal Activity Definition into an ADK-compatible tool.

    Args:
        activity_def: The Temporal activity definition (decorated with @activity.defn).
        **activity_options: Options to pass to workflow.execute_activity
                            (e.g. start_to_close_timeout, retry_policy).

    Returns:
        A callable tool that executes the activity when invoked.
    """
    
    # We create a wrapper that delegates to workflow.execute_activity
    async def tool_wrapper(*args, **kwargs) -> Any:
        # Note: ADK tools usually pass args/kwargs strictly matched to signature.
        # Activities expect positional args in a list if 'args' is used.
        # If the tool signature matches the activity signature, we can pass args.
        # It's safer if activity takes Pydantic models or simple types.
        
        # We assume strict positional argument mapping for now, or simplistic kwargs handling if supported.
        # Temporal Python SDK typically invokes activities with `args=[...]`.
        
        return await workflow.execute_activity(
            activity_def,
            args=list(args) + list(kwargs.values()) if kwargs else list(args),
            **activity_options
        )

    # Copy metadata so ADK can inspect the tool (name, docstring, annotations)
    # ADK uses this to generate the tool schema for the LLM.
    tool_wrapper.__doc__ = activity_def.__doc__
    tool_wrapper.__name__ = getattr(activity_def, "name", activity_def.__name__)
    
    # Attempt to copy annotations if they exist
    if hasattr(activity_def, "__annotations__"):
        tool_wrapper.__annotations__ = activity_def.__annotations__

    # CRITICAL: Copy signature so FunctionTool can generate correct parameters schema
    try:
        import inspect
        tool_wrapper.__signature__ = inspect.signature(activity_def)
    except Exception:
        pass  # Fallback if signature copy fails (e.g. builtins)

    return tool_wrapper


@activity.defn
async def generate_content_activity(request: LlmRequest) -> List[LlmResponse]:
    """Generic activity to invoke an LLM via ADK's LLMRegistry.
    
    The model name is expected to be in `request.model`.
    """
    if not request.model:
        raise ValueError("LlmRequest.model must be set when using generate_content_activity.")
        
    llm = LLMRegistry.new_llm(request.model)
    return [response async for response in llm.generate_content_async(request)]


class TemporalModel(BaseLlm):
    """An ADK ModelWrapper that executes content generation as a Temporal Activity.
    
    This effectively delegates the 'generate_content' call to an external Activity,
    ensuring that the network I/O to Vertex/Gemini is recorded in Temporal history.
    """
    
    activity_def: Callable
    activity_options: dict[str, Any]

    def __init__(
        self,
        model_name: str,
        activity_def: Callable = generate_content_activity,
        **activity_options: Any
    ):
        """Initializes the TemporalModel.

        Args:
            model_name: The name of the model to report to ADK.
            activity_def: The Temporal activity definition to invoke. 
                          Defaults to `generate_content_activity`.
            **activity_options: Options for workflow.execute_activity.
        """
        super().__init__(
            model=model_name,
            activity_def=activity_def,
            activity_options=activity_options
        )

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Generates content by calling the configured Temporal Activity."""
        
        # Ensure model name is carried in the request for the generic activity
        if not llm_request.model:
            llm_request.model = self.model

        # Note: Temporal Activities are not typically streaming in the Python SDK 
        # in the way python async generators work (streaming back to workflow is complex).
        # Standard approach is to return the full response. 
        # We will assume non-streaming activity execution for now.
        
        # Execute the activity
        responses: List[LlmResponse] = await workflow.execute_activity(
            self.activity_def,
            args=[llm_request],
            **self.activity_options
        )
        
        # Yield the responses
        for response in responses:
            yield response

    @classmethod
    def default_activities(cls) -> List[Callable]:
        """Returns the default activities used by this model wrapper.
        
        Useful for registering activities with the Temporal Worker.
        """
        return [generate_content_activity]
