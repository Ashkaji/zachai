"""
ZachAI — Camunda External Task Worker: Provision Label Studio
Story 2.2: Polls Camunda 7 for 'provision-label-studio' tasks,
creates a Label Studio project via its API, reports completion.
"""
import asyncio
import os
import logging
import asyncpg

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CAMUNDA_REST_URL = os.environ.get("CAMUNDA_REST_URL", "http://camunda7:8080/engine-rest")
LABEL_STUDIO_URL = os.environ.get("LABEL_STUDIO_URL", "http://label-studio:8080")
LABEL_STUDIO_API_KEY = os.environ.get("LABEL_STUDIO_API_KEY", "")
ML_BACKEND_URL = os.environ.get("ML_BACKEND_URL", "http://label-studio-ml-bridge:9090")

# Validate required environment variables
if not LABEL_STUDIO_API_KEY:
    raise ValueError(
        "LABEL_STUDIO_API_KEY environment variable is required. "
        "Get your API token from Label Studio UI: Settings → Account & Settings → API token."
    )

# DB Credentials (Story 2.2 sync)
DB_USER = os.environ.get("POSTGRES_USER", "zachai")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "zachai")
DB_NAME = os.environ.get("POSTGRES_DB", "zachai")
DB_HOST = os.environ.get("DB_HOST", "postgres")

WORKER_ID = "zachai-provision-worker"
MAX_RETRIES = 3


async def register_ml_backend_with_retry(
    client: httpx.AsyncClient, ls_project_id: int, retries: int = 3
) -> bool:
    """Register ML backend on Label Studio project with bounded retries."""
    last_status: int | None = None
    last_text: str = ""
    for attempt in range(1, retries + 1):
        try:
            ml_resp = await client.post(
                f"{LABEL_STUDIO_URL}/api/ml/",
                headers={"Authorization": f"Token {LABEL_STUDIO_API_KEY}"},
                json={
                    "url": ML_BACKEND_URL,
                    "project": ls_project_id,
                    "title": "ZachAI Whisper Pre-annotation",
                    "is_interactive": False,
                },
            )
            last_status = ml_resp.status_code
            last_text = ml_resp.text
            if ml_resp.status_code in (200, 201, 409):
                logger.info("ML backend registered for LS project %s", ls_project_id)
                return True
            logger.warning(
                "ML backend registration attempt %d/%d failed (%s): %s",
                attempt,
                retries,
                ml_resp.status_code,
                ml_resp.text[:500],
            )
        except Exception as exc:
            logger.warning(
                "ML backend registration attempt %d/%d raised: %s",
                attempt,
                retries,
                exc,
            )
        if attempt < retries:
            await asyncio.sleep(2 * attempt)

    logger.warning(
        "ML backend registration failed after retries; continuing project provisioning. "
        "status=%s body=%s",
        last_status,
        last_text[:500],
    )
    return False


async def find_existing_project_id(
    client: httpx.AsyncClient, title: str
) -> int | None:
    """Best-effort lookup to avoid duplicate LS project creation on retries."""
    try:
        resp = await client.get(
            f"{LABEL_STUDIO_URL}/api/projects/",
            headers={"Authorization": f"Token {LABEL_STUDIO_API_KEY}"},
            params={"title": title},
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if isinstance(payload, dict):
            items = payload.get("results")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("title") == title and item.get("id"):
                        return int(item["id"])
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("title") == title and item.get("id"):
                    return int(item["id"])
    except Exception as exc:
        logger.warning("Existing project lookup failed for %s: %s", title, exc)
    return None


async def sync_label_studio_id_to_db(project_id: int, ls_project_id: int) -> bool:
    """Update ZachAI database with the newly created Label Studio project ID."""
    conn = None
    try:
        conn = await asyncpg.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            host=DB_HOST
        )
        await conn.execute(
            "UPDATE projects SET label_studio_project_id = $1, updated_at = NOW() WHERE id = $2",
            ls_project_id, project_id
        )
        logger.info("Project %s synced with LS ID %s in database", project_id, ls_project_id)
        return True
    except Exception as exc:
        logger.error("Failed to sync project %s to database: %s", project_id, exc)
        return False
    finally:
        if conn:
            await conn.close()


async def process_provision_task(client: httpx.AsyncClient, task: dict) -> None:
    """Process a provision-label-studio external task."""
    task_id = task["id"]
    variables = task.get("variables", {})
    retries = task.get("retries")  # Camunda tracks remaining retries

    project_id = variables.get("projectId", {}).get("value")
    nature_name = variables.get("natureName", {}).get("value", "Untitled")
    label_schema = variables.get("labelStudioSchema", {}).get("value", "")

    logger.info("Processing task %s: project_id=%s", task_id, project_id)

    try:
        project_title = f"{nature_name} — Project {project_id}"
        ls_project_id = await find_existing_project_id(client, project_title)
        if ls_project_id is None:
            ls_resp = await client.post(
                f"{LABEL_STUDIO_URL}/api/projects/",
                headers={"Authorization": f"Token {LABEL_STUDIO_API_KEY}"},
                json={
                    "title": project_title,
                    "description": f"ZachAI Project {project_id}",
                    "label_config": label_schema,
                    "workspace": 1,  # Required by AC 4
                    "is_published": False,
                    "sampling": "Sequential",
                },
            )

            # Accept 201 Created (standard for resource creation) or 200 OK (some APIs)
            if ls_resp.status_code in (200, 201):
                ls_project_id = ls_resp.json().get("id")
                if not ls_project_id:
                    raise Exception("Label Studio response missing project id")
            elif ls_resp.status_code >= 500:
                # Server error — retryable
                remaining = (retries if retries is not None else MAX_RETRIES) - 1
                logger.warning(
                    "Label Studio 5xx (%s), reporting failure (retries left: %s)",
                    ls_resp.status_code, remaining,
                )
                await client.post(
                    f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
                    json={
                        "workerId": WORKER_ID,
                        "errorMessage": f"Label Studio server error: {ls_resp.status_code}",
                        "retries": max(remaining, 0),
                        "retryTimeout": 300_000,  # 5 min
                    },
                )
                return
            else:
                # Client error (4xx) — not retryable, mark incident
                logger.error("Label Studio 4xx (%s): %s — marking incident", ls_resp.status_code, ls_resp.text)
                await client.post(
                    f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
                    json={
                        "workerId": WORKER_ID,
                        "errorMessage": f"Label Studio rejected request: {ls_resp.status_code} {ls_resp.text}",
                        "retries": 0,  # triggers incident in Camunda Cockpit
                        "retryTimeout": 0,
                    },
                )
                return
        else:
            logger.info("Reusing existing Label Studio project %s for title=%s", ls_project_id, project_title)

        logger.info("Label Studio project ready: %s", ls_project_id)

        # Sync to ZachAI database before completing Camunda task
        db_synced = await sync_label_studio_id_to_db(project_id, ls_project_id)
        if not db_synced:
            raise Exception("Database synchronization failed")

        # Auto-register ML backend for Whisper pre-annotations (best effort)
        await register_ml_backend_with_retry(client, ls_project_id, retries=3)

        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/complete",
            json={
                "workerId": WORKER_ID,
                "variables": {
                    "labelStudioProjectId": {"value": ls_project_id, "type": "Integer"},
                },
            },
        )
        logger.info("Task %s completed successfully", task_id)

    except Exception as exc:
        logger.error("Exception processing task %s: %s", task_id, exc)
        remaining = (retries if retries is not None else MAX_RETRIES) - 1
        try:
            await client.post(
                f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
                json={
                    "workerId": WORKER_ID,
                    "errorMessage": str(exc),
                    "retries": max(remaining, 0),
                    "retryTimeout": 300_000,
                },
            )
        except Exception as inner:
            logger.error("Failed to report failure for task %s: %s", task_id, inner)


async def run() -> None:
    """Main loop: long-poll Camunda for external tasks."""
    logger.info("Starting Camunda External Task Worker (%s)", WORKER_ID)
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            try:
                resp = await client.post(
                    f"{CAMUNDA_REST_URL}/external-task/fetchAndLock",
                    json={
                        "workerId": WORKER_ID,
                        "maxTasks": 5,
                        "asyncResponseTimeout": 30_000,
                        "topics": [
                            {
                                "topicName": "provision-label-studio",
                                "lockDuration": 600_000,
                            },
                        ],
                    },
                )
                if resp.status_code == 200:
                    for task in resp.json():
                        await process_provision_task(client, task)
                else:
                    logger.warning("fetchAndLock returned %s", resp.status_code)
            except httpx.ConnectError:
                logger.warning("Camunda not reachable — retrying in 10s")
                await asyncio.sleep(10)
                continue
            except Exception as exc:
                logger.error("Unexpected error in poll loop: %s", exc)

            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
