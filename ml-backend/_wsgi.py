import os
import logging
from label_studio_ml.api import init_app
from model import AudioSegmentationModel  # IMPORT DIRECT DE LA CLASSE

# Configuration du logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Création de l'application
logger.info("Initializing Label Studio ML Backend...")

try:
    # IMPORTANT: Passez la classe directement, pas une string
    app = init_app(
        model_class=AudioSegmentationModel  # CLASSE, pas 'model.AudioSegmentationModel'
    )
    
    logger.info("ML Backend initialized successfully")
    
except Exception as e:
    logger.error(f"Failed to initialize ML Backend: {e}", exc_info=True)
    raise

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 9090))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)