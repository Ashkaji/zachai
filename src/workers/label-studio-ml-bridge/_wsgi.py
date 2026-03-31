import logging
import os

from label_studio_ml.api import init_app

from model import ZachaiOpenVinoBridge

log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))

app = init_app(model_class=ZachaiOpenVinoBridge)
