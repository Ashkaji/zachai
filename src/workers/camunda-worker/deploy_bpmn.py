"""
ZachAI — Camunda BPMN Auto-Deployment Script
Story 1.4: Scans src/bpmn for .bpmn files and deploys them to Camunda 7 REST API.
"""
import os
import logging
import httpx
import pathlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bpmn-deployer")

CAMUNDA_REST_URL = os.environ.get("CAMUNDA_REST_URL", "http://camunda7:8080/engine-rest")
BPMN_DIR = pathlib.Path(__file__).parent.parent.parent / "bpmn"

def deploy_all():
    if not BPMN_DIR.exists():
        logger.error("BPMN directory not found at %s", BPMN_DIR)
        return

    bpmn_files = list(BPMN_DIR.glob("*.bpmn"))
    if not bpmn_files:
        logger.warning("No .bpmn files found in %s", BPMN_DIR)
        return

    logger.info("Found %d BPMN files to deploy", len(bpmn_files))

    with httpx.Client(timeout=30.0) as client:
        for bpmn_path in bpmn_files:
            deployment_name = f"ZachAI-{bpmn_path.stem}"
            logger.info("Deploying %s...", bpmn_path.name)
            
            try:
                with open(bpmn_path, "rb") as f:
                    files = {"data": (bpmn_path.name, f, "application/octet-stream")}
                    data = {
                        "deployment-name": deployment_name,
                        "enable-duplicate-filtering": "true",
                        "deploy-changed-only": "true"
                    }
                    
                    resp = client.post(
                        f"{CAMUNDA_REST_URL}/deployment/create",
                        data=data,
                        files=files
                    )
                    
                if resp.status_code == 200:
                    logger.info("✅ Successfully deployed %s", bpmn_path.name)
                else:
                    logger.error("❌ Failed to deploy %s: %s - %s", 
                                 bpmn_path.name, resp.status_code, resp.text)
            except Exception as exc:
                logger.exception("❌ Error during deployment of %s: %s", bpmn_path.name, exc)

if __name__ == "__main__":
    deploy_all()
