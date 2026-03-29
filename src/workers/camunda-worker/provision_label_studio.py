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
LABEL_STUDIO_URL = os.environ.get("LABEL_STUDIO_URL", "http://label-studio:8090")
LABEL_STUDIO_API_KEY = os.environ.get("LABEL_STUDIO_API_KEY", "")

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
        ls_resp = await client.post(
            f"{LABEL_STUDIO_URL}/api/projects/",
            headers={"Authorization": f"Token {LABEL_STUDIO_API_KEY}"},
            json={
                "title": f"{nature_name} — Project {project_id}",
                "description": f"ZachAI Project {project_id}",
                "label_config": label_schema,
                "workspace": 1,  # Required by AC 4
                "is_published": False,
                "sampling": "Sequential",
            },
        )

        if 200 <= ls_resp.status_code < 300:
            ls_project_id = ls_resp.json().get("id")
            if not ls_project_id:
                raise Exception("Label Studio response missing project id")

            logger.info("Label Studio project created: %s", ls_project_id)

            # Sync to ZachAI database before completing Camunda task
            db_synced = await sync_label_studio_id_to_db(project_id, ls_project_id)
            if not db_synced:
                raise Exception("Database synchronization failed")

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
