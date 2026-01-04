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
        self.set("model_version", "audio-segmentation-v1.1")
        logger.info("✅ Setup terminé - prêt à recevoir des requêtes")
        return {
            "model_version": self.get("model_version"),
            "status": "ready",
            "message": "Modèles Whisper pré-chargés avec succès"
        }

    def predict(self, tasks: List[Dict], context: Optional[Dict] = None, **kwargs):
        """
        Prédictions - VERSION OPTIMISÉE GROS FICHIERS
        """
        logger.info("=" * 80)
        logger.info(f"🎯 PREDICT called with {len(tasks)} tasks")
        logger.info("=" * 80)
        
        # Log mémoire initiale
        self._log_memory_usage("START")
        
        # Récupérer l'API key depuis le contexte si disponible
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
                
                # 🔥 ÉTAPE 1: Télécharger (avec streaming pour gros fichiers)
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
                
                # 🔥 ÉTAPE 2: Convertir en WAV (optimisé pour gros fichiers)
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
                
                # 🔥 ÉTAPE 3: Segmentation et classification
                logger.info("\n🎯 Segmenting and classifying...")
                segments = self.segmenter.segment_and_classify(wav_path)
                
                logger.info(f"✅ Generated {len(segments)} segments")
                
                # Log détaillé des segments
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
                
                # 🔥 NETTOYAGE IMMÉDIAT + GARBAGE COLLECTION
                self._cleanup_files([audio_path, wav_path])
                gc.collect()  # Force garbage collection
                
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
        🔥 VERSION CORRIGÉE: Labels ET transcriptions dans une seule région
        """
        results = []
        
        for i, segment in enumerate(segments):
            label = segment['label']
            region_id = f"region_{i}"
            
            # 🔥 IMPORTANT: Créer UNE SEULE région avec le label
            region = {
                'id': region_id,
                'from_name': 'label',
                'to_name': 'audio',
                'type': 'labels',
                'value': {
                    'start': segment['start'],
                    'end': segment['end'],
                    'labels': [label]
                },
                'score': segment.get('confidence', 0.8)
            }
            
            results.append(region)
            
            # 🔥 FIX CRITIQUE: Transcription attachée à la MÊME région
            # Utiliser 'origin' pour lier la transcription à la région du label
            if label == 'speech' and segment.get('transcription'):
                transcription = {
                    'id': f"trans_{i}",
                    'from_name': 'transcription',
                    'to_name': 'audio',
                    'type': 'textarea',
                    'origin': 'manual',  # Important pour Label Studio
                    'value': {
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': [segment['transcription']]
                    }
                }
                
                results.append(transcription)
            
            # Debug: Log si on a une incohérence
            if label == 'silence' and segment.get('transcription'):
                logger.warning(f"⚠️ Segment {i}: silence has transcription (should not happen!)")
            if label == 'noise' and segment.get('transcription'):
                logger.warning(f"⚠️ Segment {i}: noise has transcription (should not happen!)")
        
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
                    logger.debug(f"🗑️  Removed: {path}")
            except Exception as e:
                logger.debug(f"Could not remove {path}: {e}")
    
    def _log_memory_usage(self, stage: str):
        """Log l'utilisation mémoire"""
        try:
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            
            # Mémoire système
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
        speech_count = sum(1 for s in segments if s['label'] == 'speech')
        noise_count = sum(1 for s in segments if s['label'] == 'noise')
        silence_count = sum(1 for s in segments if s['label'] == 'silence')
        
        # Durées totales
        speech_duration = sum(s['end'] - s['start'] for s in segments if s['label'] == 'speech')
        noise_duration = sum(s['end'] - s['start'] for s in segments if s['label'] == 'noise')
        silence_duration = sum(s['end'] - s['start'] for s in segments if s['label'] == 'silence')
        
        total_duration = speech_duration + noise_duration + silence_duration
        
        logger.info(f"\n📊 SEGMENT SUMMARY:")
        logger.info(f"   Total segments: {len(segments)}")
        logger.info(f"   Speech:  {speech_count:3d} segments ({speech_duration:6.1f}s = {100*speech_duration/total_duration:5.1f}%)")
        logger.info(f"   Noise:   {noise_count:3d} segments ({noise_duration:6.1f}s = {100*noise_duration/total_duration:5.1f}%)")
        logger.info(f"   Silence: {silence_count:3d} segments ({silence_duration:6.1f}s = {100*silence_duration/total_duration:5.1f}%)")
        logger.info(f"   Total duration: {total_duration:.1f}s")
        
        # Log quelques transcriptions d'exemple
        speech_with_trans = [s for s in segments if s['label'] == 'speech' and s.get('transcription')]
        if speech_with_trans:
            logger.info(f"\n📝 Sample transcriptions:")
            for i, seg in enumerate(speech_with_trans[:3], 1):
                trans = seg['transcription'][:80]
                logger.info(f"   {i}. [{seg['start']:.1f}s] ({seg.get('language', '?')}) {trans}...")
    
    def fit(self, event, data, **kwargs):
        """Active Learning - pour plus tard"""
        logger.info(f"Fit called: {event}")
        return {'model_version': self.get("model_version")}