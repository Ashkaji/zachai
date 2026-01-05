import torch
import torchaudio
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional, Iterator
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import os

logger = logging.getLogger(__name__)


class AudioSegmenter:
    """
    Segmenteur audio optimisé pour GROS FICHIERS (100MB+)
    - Traitement en STREAMING (pas d'attente du chargement complet)
    - Détection UNIQUEMENT de la parole (pas de labels noise/silence)
    - Transcription progressive segment par segment
    """
    
    def __init__(self, max_duration: float = 30.0):
        self.max_duration = max_duration
        self.sample_rate = 16000
        
        # Modèles - initialisés à None
        self.asr_model = None
        self.asr_processor = None
        self.device = None
        
        # 🔥 NOUVEAUX SEUILS - Plus permissifs pour détecter plus de parole
        self.silence_thresh = -35  # dBFS (était -40, maintenant moins strict)
        self.min_silence_len = 400  # ms (était 300, maintenant plus long)
        self.min_speech_duration = 0.5  # secondes minimum pour garder un segment
        
        # Langues supportées
        self.languages = ["fr", "en", "es", "de", "it", "pt"]

    def load_models(self):
        """Charge les modèles Whisper depuis le cache local"""
        if self.asr_model is not None:
            return  # Déjà chargé
            
        try:
            logger.info("=" * 80)
            logger.info("🚀 Chargement du modèle Whisper...")
            logger.info("=" * 80)
            
            local_model_path = "/app/models/whisper-tiny"
            
            logger.info(f"📂 Recherche dans: {local_model_path}")
            
            if os.path.exists(local_model_path):
                files = os.listdir(local_model_path)
                logger.info(f"   Fichiers trouvés: {len(files)}")
                
                required_files = ['config.json', 'preprocessor_config.json']
                model_file = None
                
                for f in files:
                    if f in required_files:
                        logger.info(f"   ✓ {f}")
                    if f.endswith('.bin') or f.endswith('.safetensors'):
                        model_file = f
                        size_mb = os.path.getsize(os.path.join(local_model_path, f)) / 1024 / 1024
                        logger.info(f"   ✓ {f} ({size_mb:.1f} MB)")
                
                if model_file and all(os.path.exists(os.path.join(local_model_path, f)) for f in required_files):
                    logger.info("✅ Modèle complet trouvé localement")
                    logger.info("")
                    
                    logger.info("⏳ Chargement du Processor...")
                    self.asr_processor = WhisperProcessor.from_pretrained(
                        local_model_path,
                        local_files_only=True
                    )
                    logger.info("✅ Processor chargé")
                    
                    logger.info("⏳ Chargement du Model...")
                    self.asr_model = WhisperForConditionalGeneration.from_pretrained(
                        local_model_path,
                        local_files_only=True
                    )
                    logger.info("✅ Model chargé")
                    
                else:
                    raise FileNotFoundError(f"Fichiers du modèle incomplets dans {local_model_path}")
                    
            else:
                raise FileNotFoundError(f"Dossier {local_model_path} introuvable")
            
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"🖥️ Device: {self.device}")
            
            self.asr_model.to(self.device)
            
            logger.info("=" * 80)
            logger.info("✅ Modèle Whisper chargé avec succès!")
            logger.info("=" * 80)
            logger.info("")
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error("❌ ERREUR lors du chargement des modèles")
            logger.error("=" * 80)
            logger.error(f"{e}", exc_info=True)
            self.asr_model = None
            self.asr_processor = None

    def segment_and_classify_streaming(self, audio_path: str) -> Iterator[Dict]:
        """
        🔥 NOUVELLE VERSION STREAMING
        Yield les segments au fur et à mesure du traitement
        Pas d'attente du chargement complet de l'audio
        
        Yields:
            Dict: Segment de parole avec transcription
                {
                    'start': float,
                    'end': float,
                    'transcription': str,
                    'language': str,
                    'confidence': float
                }
        """
        try:
            logger.info(f"🎬 Démarrage traitement STREAMING: {audio_path}")
            
            # 1. Charger l'audio (nécessaire pour detect_nonsilent)
            # TODO: Pour des fichiers VRAIMENT énormes (1GB+), on pourrait
            # faire du chunking audio direct, mais pydub est déjà optimisé
            logger.info("📂 Chargement audio...")
            audio = AudioSegment.from_file(audio_path)
            duration_sec = len(audio) / 1000.0
            
            logger.info(f"✅ Audio chargé: {duration_sec:.2f}s, {audio.frame_rate}Hz")
            
            # 2. Détection des zones de PAROLE uniquement
            logger.info("🔍 Détection des zones de parole...")
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=self.min_silence_len,
                silence_thresh=self.silence_thresh,
                seek_step=50
            )
            
            logger.info(f"✅ Trouvé {len(nonsilent_ranges)} zones de parole potentielles")
            
            if not nonsilent_ranges:
                logger.warning("⚠️ Aucune zone de parole détectée dans cet audio")
                return
            
            # 3. 🔥 TRAITER CHAQUE SEGMENT IMMÉDIATEMENT (streaming)
            segments_yielded = 0
            
            for i, (start_ms, end_ms) in enumerate(nonsilent_ranges, 1):
                start_sec = start_ms / 1000.0
                end_sec = end_ms / 1000.0
                duration = end_sec - start_sec
                
                # Filtrer les segments trop courts (probablement du bruit)
                if duration < self.min_speech_duration:
                    logger.debug(f"⏭️ Segment {i} ignoré (trop court: {duration:.2f}s)")
                    continue
                
                logger.info(f"\n{'─' * 60}")
                logger.info(f"🎤 Segment {i}/{len(nonsilent_ranges)} [{start_sec:.1f}s - {end_sec:.1f}s] ({duration:.1f}s)")
                
                # Si le segment est trop long, le découper
                if duration > self.max_duration:
                    logger.info(f"✂️ Segment long, découpage en chunks de {self.max_duration}s")
                    
                    for chunk_segment in self._split_and_process_long_segment(
                        audio, start_ms, end_ms, i
                    ):
                        segments_yielded += 1
                        yield chunk_segment
                else:
                    # Extraire et traiter directement
                    segment_audio = audio[start_ms:end_ms]
                    
                    # Transcrire immédiatement
                    transcription, language, confidence = self._transcribe_segment_whisper(
                        segment_audio
                    )
                    
                    # Vérifier que c'est bien de la parole
                    if transcription and len(transcription.strip()) > 0 and confidence > 0.3:
                        segment = {
                            'start': start_sec,
                            'end': end_sec,
                            'transcription': transcription.strip(),
                            'language': language,
                            'confidence': confidence
                        }
                        
                        logger.info(f"✅ ({language}) \"{transcription[:60]}...\" (conf: {confidence:.2f})")
                        
                        segments_yielded += 1
                        yield segment
                    else:
                        logger.debug(f"⏭️ Segment {i} rejeté (pas de transcription valide)")
            
            logger.info(f"\n{'=' * 60}")
            logger.info(f"🎉 Traitement terminé: {segments_yielded} segments de parole détectés")
            logger.info(f"{'=' * 60}")
            
        except Exception as e:
            logger.error(f"❌ Erreur dans segment_and_classify_streaming: {e}", exc_info=True)
            # Ne pas yield de segments en cas d'erreur
            return
    
    def segment_and_classify(self, audio_path: str) -> List[Dict]:
        """
        Version NON-STREAMING (pour compatibilité)
        Collecte tous les segments avant de retourner
        """
        segments = list(self.segment_and_classify_streaming(audio_path))
        logger.info(f"✅ Collecté {len(segments)} segments au total")
        return segments
    
    def _split_and_process_long_segment(
        self,
        audio: AudioSegment,
        start_ms: int,
        end_ms: int,
        segment_index: int
    ) -> Iterator[Dict]:
        """
        Découpe un segment long en chunks et les traite immédiatement
        """
        chunk_duration_ms = int(self.max_duration * 1000)
        current_start = start_ms
        chunk_num = 1
        
        while current_start < end_ms:
            current_end = min(current_start + chunk_duration_ms, end_ms)
            
            logger.info(f"  📦 Chunk {chunk_num}: [{current_start/1000:.1f}s - {current_end/1000:.1f}s]")
            
            segment_audio = audio[current_start:current_end]
            
            # Transcrire immédiatement
            transcription, language, confidence = self._transcribe_segment_whisper(
                segment_audio
            )
            
            if transcription and len(transcription.strip()) > 0 and confidence > 0.3:
                segment = {
                    'start': current_start / 1000.0,
                    'end': current_end / 1000.0,
                    'transcription': transcription.strip(),
                    'language': language,
                    'confidence': confidence
                }
                
                logger.info(f"  ✅ ({language}) \"{transcription[:50]}...\" (conf: {confidence:.2f})")
                
                yield segment
            else:
                logger.debug(f"  ⏭️ Chunk {chunk_num} rejeté (pas de transcription)")
            
            current_start = current_end
            chunk_num += 1
    
    def _transcribe_segment_whisper(
        self,
        segment_audio: AudioSegment
    ) -> Tuple[str, str, float]:
        """
        Transcrit un segment audio avec Whisper
        Détection automatique de langue
        """
        if self.asr_model is None:
            logger.warning("⚠️ Whisper non chargé")
            return "", "unknown", 0.0
        
        try:
            # Convertir en array numpy et normaliser
            samples = np.array(segment_audio.get_array_of_samples())
            
            if segment_audio.sample_width == 2:  # 16-bit
                samples = samples.astype(np.float32) / 32768.0
            elif segment_audio.sample_width == 4:  # 32-bit
                samples = samples.astype(np.float32) / 2147483648.0
            
            # Rééchantillonner à 16kHz si nécessaire
            if segment_audio.frame_rate != self.sample_rate:
                audio_tensor = torch.from_numpy(samples).float()
                if len(audio_tensor.shape) == 1:
                    audio_tensor = audio_tensor.unsqueeze(0)
                
                resampler = torchaudio.transforms.Resample(
                    orig_freq=segment_audio.frame_rate,
                    new_freq=self.sample_rate
                )
                audio_tensor = resampler(audio_tensor)
                samples = audio_tensor.squeeze().numpy()
            
            # Préparer l'input pour Whisper
            inputs = self.asr_processor(
                samples,
                sampling_rate=self.sample_rate,
                return_tensors="pt"
            )
            
            input_features = inputs.input_features.to(self.device)
            
            # Générer avec détection automatique de langue
            with torch.no_grad():
                predicted_ids = self.asr_model.generate(
                    input_features,
                    task="transcribe",
                    language=None,  # Détection auto
                    max_length=225
                )
            
            # Détecter la langue
            language_token = predicted_ids[0][0].item()
            
            # Mapping simplifié des tokens de langue
            language_map = {
                50258: "fr", 50259: "en", 50260: "de", 50261: "es",
                50262: "it", 50263: "pt", 50264: "ru", 50265: "zh",
                50266: "ja", 50267: "ko", 50268: "ar", 50269: "hi"
            }
            
            detected_language = language_map.get(language_token, "unknown")
            
            if detected_language == "unknown":
                try:
                    lang_str = self.asr_processor.tokenizer.decode([language_token])
                    if lang_str.startswith("<|") and lang_str.endswith("|>"):
                        detected_language = lang_str[2:-2]
                except:
                    detected_language = "unknown"
            
            # Décoder la transcription
            transcription = self.asr_processor.batch_decode(
                predicted_ids,
                skip_special_tokens=True
            )[0]
            
            # Calculer confiance approximative
            confidence = min(0.95, 0.5 + len(transcription) / 200)
            
            return transcription.strip(), detected_language, confidence
            
        except Exception as e:
            logger.error(f"❌ Erreur transcription Whisper: {e}")
            return "", "unknown", 0.0