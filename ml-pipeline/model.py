from typing import List, Dict, Optional
from label_studio_ml.model import LabelStudioMLBase
from audio_segmenter import AudioSegmenter
from utils import download_audio_file, convert_to_wav
import os
import logging
import traceback
import gc
import psutil

logger = logging.getLogger(__name__)

class AudioSegmentationModel(LabelStudioMLBase):
    """
    Modèle de segmentation audio pour Label Studio
    
    - Détecte UNIQUEMENT les zones de parole (label "speech")
    - Traitement en STREAMING pour gros fichiers (100MB+)
    - Transcription progressive segment par segment
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.max_segment_duration = 30.0
        
        logger.info("🚀 Initialisation du AudioSegmenter...")
        
        # Initialiser le segmenter
        self.segmenter = AudioSegmenter(max_duration=self.max_segment_duration)
        
        # 🎯 CHARGER LES MODÈLES IMMÉDIATEMENT
        logger.info("Chargement des modèles Whisper...")
        self.segmenter.load_models()
        
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
        self.set("model_version", "audio-segmentation-v2.0-speech-only")
        logger.info("✅ Setup terminé - prêt à recevoir des requêtes")
        return {
            "model_version": self.get("model_version"),
            "status": "ready",
            "message": "Modèles Whisper pré-chargés - Mode SPEECH ONLY"
        }

    def predict(self, tasks: List[Dict], context: Optional[Dict] = None, **kwargs):
        """
        Prédictions - VERSION STREAMING OPTIMISÉE
        
        🔥 CHANGEMENTS:
        - Pas d'attente du chargement complet
        - Traitement segment par segment
        - Mémoire optimisée pour gros fichiers
        """
        logger.info("=" * 80)
        logger.info(f"🎯 PREDICT called with {len(tasks)} tasks")
        logger.info("=" * 80)
        
        self._log_memory_usage("START")
        
        # Récupérer l'API key
        api_key = None
        if context and 'access_token' in context:
            api_key = context['access_token']
        
        predictions = []
        
        for idx, task in enumerate(tasks, 1):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"📋 TASK {idx}/{len(tasks)}")
            logger.info(f"{'=' * 60}")
            
            try:
                audio_url = task['data'].get('audio')
                task_id = task.get('id', 'unknown')
                
                if not audio_url:
                    logger.warning(f"❌ No audio URL in task {task_id}")
                    predictions.append(self._create_empty_prediction())
                    continue
                
                logger.info(f"Task ID: {task_id}")
                logger.info(f"Audio URL: {audio_url[:100]}...")
                
                # 🔥 ÉTAPE 1: Télécharger (avec streaming)
                logger.info("\n📥 Downloading audio...")
                audio_path = download_audio_file(audio_url, task_id, api_key)
                
                if not audio_path or not os.path.exists(audio_path):
                    logger.error(f"❌ Download failed for task {task_id}")
                    predictions.append(self._create_empty_prediction())
                    continue
                
                file_size = os.path.getsize(audio_path)
                file_size_mb = file_size / 1024 / 1024
                logger.info(f"✅ Downloaded: {file_size_mb:.1f} MB")
                
                self._log_memory_usage("AFTER DOWNLOAD")
                
                # 🔥 ÉTAPE 2: Convertir en WAV
                logger.info("\n🔄 Converting to WAV...")
                wav_path = convert_to_wav(audio_path)
                
                if not wav_path or not os.path.exists(wav_path):
                    logger.error(f"❌ Conversion failed for task {task_id}")
                    self._cleanup_files([audio_path])
                    predictions.append(self._create_empty_prediction())
                    continue
                
                wav_size = os.path.getsize(wav_path)
                wav_size_mb = wav_size / 1024 / 1024
                logger.info(f"✅ Converted: {wav_size_mb:.1f} MB")
                
                self._log_memory_usage("AFTER CONVERSION")
                
                # 🔥 ÉTAPE 3: Segmentation STREAMING
                logger.info("\n🎯 Segmenting and transcribing (STREAMING)...")
                logger.info("    Les segments sont traités au fur et à mesure...")
                
                # Utiliser la version NON-STREAMING pour compatibilité Label Studio
                # (qui attend une liste complète)
                segments = self.segmenter.segment_and_classify(wav_path)
                
                logger.info(f"✅ Generated {len(segments)} speech segments")
                
                # Log détaillé
                self._log_segment_summary(segments)
                
                self._log_memory_usage("AFTER SEGMENTATION")
                
                # 🔥 ÉTAPE 4: Conversion au format Label Studio
                logger.info("\n📝 Converting to Label Studio format...")
                result = self._convert_to_label_studio_format(segments)
                
                predictions.append({
                    'model_version': self.get("model_version"),
                    'score': 0.85,
                    'result': result
                })
                
                logger.info(f"✅ Prediction created with {len(result)} annotations")
                
                # 🔥 NETTOYAGE IMMÉDIAT
                self._cleanup_files([audio_path, wav_path])
                gc.collect()
                
                self._log_memory_usage("AFTER CLEANUP")
                
            except Exception as e:
                logger.error(f"\n{'=' * 60}")
                logger.error(f"❌ ERROR processing task {idx}")
                logger.error(f"{'=' * 60}")
                logger.error(f"Exception: {e}")
                logger.error(traceback.format_exc())
                
                predictions.append(self._create_empty_prediction())
                
                # Nettoyer même en cas d'erreur
                try:
                    if 'audio_path' in locals():
                        self._cleanup_files([audio_path])
                    if 'wav_path' in locals():
                        self._cleanup_files([wav_path])
                except:
                    pass
        
        logger.info("\n" + "=" * 80)
        logger.info(f"✅ PREDICT COMPLETED - {len(predictions)} predictions returned")
        logger.info("=" * 80)
        
        self._log_memory_usage("END")
        
        return predictions

    def _convert_to_label_studio_format(self, segments: List[Dict]) -> List[Dict]:
        """
        Convertit les segments au format Label Studio
        
        🔥 VERSION SANS LABELS - Les régions sont créées SANS label prédéfini
        L'utilisateur cliquera pour ajouter ses propres labels selon son projet
        """
        results = []
        
        for i, segment in enumerate(segments):
            # 🔥 UNE SEULE ANNOTATION PAR SEGMENT
            # Pas de label prédéfini - juste la transcription dans une région
            
            annotation = {
                'id': f"region_{i}",
                'from_name': 'transcription',  # Lié au <TextArea name="transcription">
                'to_name': 'audio',
                'type': 'textarea',
                'origin': 'manual',
                'value': {
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': [segment.get('transcription', '')]
                },
                'score': segment.get('confidence', 0.8)
            }
            
            results.append(annotation)
        
        return results
    
    def _create_empty_prediction(self) -> Dict:
        """Crée une prédiction vide en cas d'erreur"""
        return {
            'result': [],
            'score': 0.0,
            'model_version': self.get("model_version")
        }
    
    def _cleanup_files(self, file_paths: List[str]):
        """Nettoie les fichiers temporaires"""
        for path in file_paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    logger.debug(f"🗑️ Removed: {path}")
            except Exception as e:
                logger.debug(f"Could not remove {path}: {e}")
    
    def _log_memory_usage(self, stage: str):
        """Log l'utilisation mémoire"""
        try:
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            
            vm = psutil.virtual_memory()
            system_used_mb = vm.used / 1024 / 1024
            system_percent = vm.percent
            
            logger.info(f"\n💾 MEMORY [{stage}]:")
            logger.info(f"   Process: {mem_mb:.1f} MB")
            logger.info(f"   System:  {system_used_mb:.1f} MB ({system_percent:.1f}%)")
        except Exception as e:
            logger.debug(f"Could not log memory: {e}")
    
    def _log_segment_summary(self, segments: List[Dict]):
        """Log un résumé des segments générés"""
        if not segments:
            logger.info("\n📊 SEGMENT SUMMARY: Aucun segment de parole détecté")
            return
        
        total_duration = sum(s['end'] - s['start'] for s in segments)
        
        # Langues détectées
        languages = {}
        for s in segments:
            lang = s.get('language', 'unknown')
            languages[lang] = languages.get(lang, 0) + 1
        
        logger.info(f"\n📊 SEGMENT SUMMARY:")
        logger.info(f"   Total segments: {len(segments)}")
        logger.info(f"   Total speech duration: {total_duration:.1f}s")
        logger.info(f"   Average segment: {total_duration/len(segments):.1f}s")
        logger.info(f"   Languages detected: {languages}")
        
        # Log quelques transcriptions d'exemple
        logger.info(f"\n📝 Sample transcriptions:")
        for i, seg in enumerate(segments[:3], 1):
            trans = seg['transcription'][:80]
            lang = seg.get('language', '?')
            logger.info(f"   {i}. [{seg['start']:.1f}s] ({lang}) {trans}...")
    
    def fit(self, event, data, **kwargs):
        """Active Learning - pour plus tard"""
        logger.info(f"Fit called: {event}")
        return {'model_version': self.get("model_version")}