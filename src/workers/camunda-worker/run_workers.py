"""
Run provision-label-studio and LoRA pipeline external-task loops in one process (Story 4.4).
Includes automated BPMN deployment on startup (Story 1.4).
"""
import asyncio
import logging
import time
import httpx
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CAMUNDA_REST_URL = os.environ.get("CAMUNDA_REST_URL", "http://camunda7:8080/engine-rest")

async def wait_for_camunda():
    """Wait for Camunda REST API to be available before deploying."""
    logger.info("Waiting for Camunda REST API at %s...", CAMUNDA_REST_URL)
    async with httpx.AsyncClient() as client:
        for i in range(30):
            try:
                resp = await client.get(f"{CAMUNDA_REST_URL}/version")
                if resp.status_code == 200:
                    logger.info("Camunda is UP (version: %s)", resp.json().get("version"))
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
    logger.error("Camunda REST API timed out")
    return False

async def main() -> None:
    import provision_label_studio
    import lora_pipeline
    from deploy_bpmn import deploy_all

    # Story 1.4: Auto-deploy BPMN files
    if await wait_for_camunda():
        logger.info("Deploying BPMN definitions...")
        deploy_all()
    else:
        logger.warning("BPMN deployment skipped (Camunda not reachable)")

    logger.info("Starting combined Camunda workers (provision + LoRA pipeline)")
    await asyncio.gather(
        provision_label_studio.run(),
        lora_pipeline.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
