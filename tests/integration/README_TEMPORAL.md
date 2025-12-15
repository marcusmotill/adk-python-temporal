# Temporal Integration Tests

The file `manual_test_temporal_integration.py` contains integration tests for ADK's Temporal support.
It is named `manual_test_...` to be excluded from standard CI/test runs because it requires:

1.  **Local Temporal Server**: You must have a Temporal server running locally (e.g., via `temporal server start-dev`).
2.  **GCP Credentials**: Environment variables `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` must be set.
3.  **Local Environment**: It assumes `localhost:7233`.

## How to Run

1.  Start Temporal Server:
    ```bash
    temporal server start-dev
    ```

2.  Run the test directly:
    ```bash
    export GOOGLE_CLOUD_PROJECT="your-project"
    export GOOGLE_CLOUD_LOCATION="us-central1"
    
    uv run pytest tests/integration/manual_test_temporal_integration.py
    ```
