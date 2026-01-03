from typing import List, Dict, Optional
from label_studio_ml.model import LabelStudioMLBase
from audio_segmenter import AudioSegmenter
from utils import download_audio_file, convert_to_wav
import os
import logging
import traceback

logger = logging.getLogger(__name__)

class AudioSegmentationModel(LabelStudioMLBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.max_segment_duration = 30.0
        self.labels = ["speech", "noise", "silence"]
        
        logger.info("🚀 Initialisation du AudioSegmenter...")
        
        # Initialiser le segmenter
        self.segmenter = AudioSegmenter(max_duration=self.max_segment_duration)
        
        # 🎯 CHARGER LES MODÈLES IMMÉDIATEMENT
        logger.info("Chargement des modèles...")
        self.segmenter.load_models()
        
        # Vérifier si les modèles sont chargés
        if self.segmenter.asr_model:
            logger.info("✅ Modèles chargés avec succès")
        else:
            logger.error("❌ Échec du chargement des modèles")
            logger.error("   Vérifiez que download_models.py a bien fonctionné")
    @property
    def models_loaded(self):
        """Vérifie si les modèles Whisper sont chargés"""
        return self.segmenter is not None and self.segmenter.asr_model is not None
    
    def setup(self):
        """Setup minimal - rapide car modèles déjà chargés"""
        self.set("model_version", "audio-segmentation-v1")
        logger.info("✅ Setup terminé - prêt à recevoir des requêtes")
        return {
            "model_version": self.get("model_version"),
            "status": "ready",
            "message": "Modèles Whisper pré-chargés avec succès"
        }

    def predict(self, tasks: List[Dict], context: Optional[Dict] = None, **kwargs):
        """Prédictions - version simplifiée"""
        logger.info(f"🎯 PREDICT called with {len(tasks)} tasks")
        
        # Récupérer l'API key depuis le contexte si disponible
        api_key = None
        if context and 'access_token' in context:
            api_key = context['access_token']
        
        predictions = []
        
        for task in tasks:
            try:
                audio_url = task['data'].get('audio')
                task_id = task.get('id', 'unknown')
                
                if not audio_url:
                    logger.warning(f"No audio URL in task {task_id}")
                    continue
                
                logger.info(f"Processing task {task_id}")
                
                # Télécharger (api_key peut être None)
                audio_path = download_audio_file(audio_url, task_id, api_key)
                wav_path = convert_to_wav(audio_path)
                
                # Traitement
                segments = self.segmenter.segment_and_classify(wav_path)
                logger.info(f"Generated {len(segments)} segments")
                
                # Format Label Studio
                result = self._convert_to_label_studio_format(segments)
                
                predictions.append({
                    'model_version': self.get("model_version"),
                    'score': 0.85,
                    'result': result
                })
                
                # Nettoyer
                self._cleanup_files([audio_path, wav_path])
                
            except Exception as e:
                logger.error(f"Error processing task: {e}")
                predictions.append({
                    'result': [],
                    'score': 0.0,
                    'model_version': self.get("model_version")
                })
        
        return predictions

    def _convert_to_label_studio_format(self, segments: List[Dict]) -> List[Dict]:
        """Convertit les segments au format Label Studio"""
        results = []
        
        for i, segment in enumerate(segments):
            # Résultat de classification
            results.append({
                'id': f"seg_{i}",
                'from_name': 'label',
                'to_name': 'audio',
                'type': 'labels',
                'value': {
                    'start': segment['start'],
                    'end': segment['end'],
                    'labels': [segment['label']]
                },
                'score': segment.get('confidence', 0.8)
            })
            
            # Transcription si disponible
            if segment.get('transcription'):
                results.append({
                    'id': f"trans_{i}",
                    'from_name': 'transcription',
                    'to_name': 'audio',
                    'type': 'textarea',
                    'value': {
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': [segment['transcription']]
                    }
                })
        
        return results
    
    def _cleanup_files(self, file_paths: List[str]):
        """Nettoie les fichiers temporaires"""
        for path in file_paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    logger.debug(f"Removed temp file: {path}")
            except Exception as e:
                logger.debug(f"Could not remove {path}: {e}")
    
    def fit(self, event, data, **kwargs):
        """Active Learning - pour plus tard"""
        logger.info(f"Fit called: {event}")
        return {'model_version': self.get("model_version")}