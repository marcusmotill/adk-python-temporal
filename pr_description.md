# Refactor: Temporal Integration Cleanup & Documentation

## Summary
This PR refactors the `TemporalPlugin` to remove implicit default configurations and adds comprehensive documentation for the ADK-Temporal integration. The goal is to make the integration stricter, clearer, and easier to debug by forcing explicit configuration from the user.

## Key Changes

### 1. `TemporalPlugin` Refactor
*   **Removed Implicit Defaults**: The plugin no longer contains hardcoded default timeouts (previously 60s) or retry policies. Users must now explicitly provide `activity_options` when initializing the plugin.
*   **Removed Magic Model Resolution**: Removed the fallback logic that attempted to guess the model name from the agent context if missing. Failed requests will now raise a clear `ValueError` instead of behaving unpredictably.
*   **Simplified `before_model_callback`**: The interception hook is now a pure passthrough to `workflow.execute_activity` without additional logic or conditional checks (`workflow.in_workflow()` check removed to fail fast if misused).

### 2. Documentation (`README.md`)
*   Added a new `src/google/adk/integrations/temporal/README.md`.
*   **Internals Explained**: Documented the "Interception Flow" (how it short-circuits ADK) and "Dynamic Activities" (how `AgentName.generate_content` works without registration).
*   **Clear Usage Examples**: provided distinct, copy-pasteable snippets for **Agent Setup** (Workflow side) and **Worker Setup**, clarifying the role of `AdkWorkerPlugin`.

## Impact
*   **Safety**: Impossible to accidentally run with unsafe defaults.
*   **Debuggability**: Errors are now explicit (missing options, missing model).
*   **Clarity**: Users understand exactly *why* they are adding plugins (serialization, runtime determinism, activity routing) via the new docs.

## Usage Example

### Agent Side
```python
# You MUST now provide explicit options
activity_options = {
    "start_to_close_timeout": timedelta(minutes=1),
    "retry_policy": RetryPolicy(maximum_attempts=3)
}

agent = Agent(
    model="gemini-2.5-pro",
    plugins=[
        # Routes model calls to Temporal Activities
        TemporalPlugin(activity_options=activity_options)
    ]
)
```

### Worker Side
```python
worker = Worker(
    client,
    task_queue="my-queue",
    # Configures ADK Runtime, Pydantic Support & Unsandboxed Runner
    plugins=[AdkWorkerPlugin()]
)
```
