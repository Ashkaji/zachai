"""
Run provision-label-studio and LoRA pipeline external-task loops in one process (Story 4.4).
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    import provision_label_studio
    import lora_pipeline

    logger.info("Starting combined Camunda workers (provision + LoRA pipeline)")
    await asyncio.gather(
        provision_label_studio.run(),
        lora_pipeline.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
