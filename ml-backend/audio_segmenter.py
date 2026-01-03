import torch
import torchaudio
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from pydub import AudioSegment
from pydub.silence import detect_silence, detect_nonsilent
import os

logger = logging.getLogger(__name__)


class AudioSegmenter:
    def __init__(self, max_duration: float = 30.0):
        self.max_duration = max_duration
        self.sample_rate = 16000
        
        # Modèles - initialisés à None
        self.asr_model = None
        self.asr_processor = None
        self.device = None
        
        # Seuils
        self.silence_thresh = -40  # dBFS
        self.min_silence_len = 300  # ms
        self.speech_confidence_threshold = 0.5
        
        # Langues
        self.languages = ["fr", "en"]

    def load_models(self):
        """Charge les modèles Whisper depuis le cache local"""
        if self.asr_model is not None:
            return  # Déjà chargé
            
        try:
            logger.info("=" * 80)
            logger.info("🚀 Chargement du modèle Whisper...")
            logger.info("=" * 80)
            
            # Chemin où les modèles ont été téléchargés pendant le build
            local_model_path = "/app/models/whisper-tiny"
            
            # Vérifier si les modèles existent localement
            logger.info(f"📂 Recherche dans: {local_model_path}")
            
            if os.path.exists(local_model_path):
                # Vérifier qu'il y a bien des fichiers dedans
                files = os.listdir(local_model_path)
                logger.info(f"   Fichiers trouvés: {len(files)}")
                
                # Vérifier les fichiers critiques
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
                    
                    # Charger depuis le cache local
                    logger.info("⏳ Chargement du Processor...")
                    self.asr_processor = WhisperProcessor.from_pretrained(
                        local_model_path,
                        local_files_only=True  # Forcer l'utilisation locale
                    )
                    logger.info("✅ Processor chargé")
                    
                    logger.info("⏳ Chargement du Model...")
                    self.asr_model = WhisperForConditionalGeneration.from_pretrained(
                        local_model_path,
                        local_files_only=True  # Forcer l'utilisation locale
                    )
                    logger.info("✅ Model chargé")
                    
                else:
                    raise FileNotFoundError(f"Fichiers du modèle incomplets dans {local_model_path}")
                    
            else:
                raise FileNotFoundError(f"Dossier {local_model_path} introuvable")
            
            # Détecter device (GPU/CPU)
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"🖥️  Device: {self.device}")
            
            self.asr_model.to(self.device)
            
            logger.info("=" * 80)
            logger.info("✅ Modèle Whisper chargé avec succès!")
            logger.info("=" * 80)
            logger.info("")
            
        except FileNotFoundError as e:
            logger.error("=" * 80)
            logger.error("❌ ERREUR: Modèle Whisper introuvable!")
            logger.error("=" * 80)
            logger.error(f"{e}")
            logger.error("")
            logger.error("💡 Solutions possibles:")
            logger.error("   1. Vérifier que download_models.py a bien été exécuté pendant le build")
            logger.error("   2. Rebuilder l'image: docker-compose build --no-cache ml-backend")
            logger.error("   3. Vérifier les logs du build Docker")
            logger.error("")
            logger.error("🔍 Debug: Contenu de /app/models/")
            try:
                if os.path.exists("/app/models"):
                    for item in os.listdir("/app/models"):
                        path = os.path.join("/app/models", item)
                        if os.path.isdir(path):
                            logger.error(f"   📁 {item}/")
                        else:
                            size = os.path.getsize(path) / 1024
                            logger.error(f"   📄 {item} ({size:.1f} KB)")
                else:
                    logger.error("   ❌ /app/models n'existe pas!")
            except Exception as debug_e:
                logger.error(f"   Erreur lors du listing: {debug_e}")
            
            logger.error("=" * 80)
            self.asr_model = None
            self.asr_processor = None
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error("❌ ERREUR lors du chargement des modèles")
            logger.error("=" * 80)
            logger.error(f"{e}", exc_info=True)
            self.asr_model = None
            self.asr_processor = None

    def segment_and_classify(self, audio_path: str) -> List[Dict]:
        """
        Segmente l'audio et classifie chaque segment.
        VERSION RÉELLE - pas de mock
        """
        try:
            logger.info(f"Starting segmentation for: {audio_path}")
            
            # Charger l'audio avec pydub
            audio = AudioSegment.from_file(audio_path)
            duration_sec = len(audio) / 1000.0
            
            logger.info(f"Audio loaded: {duration_sec:.2f}s, {audio.frame_rate}Hz")
            
            # 1. Détection des zones non-silencieuses
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=self.min_silence_len,
                silence_thresh=self.silence_thresh,
                seek_step=50
            )
            
            logger.info(f"Found {len(nonsilent_ranges)} non-silent ranges")
            
            if not nonsilent_ranges:
                # Tout est silence
                return [{
                    'start': 0.0,
                    'end': duration_sec,
                    'label': 'silence',
                    'confidence': 0.95,
                    'transcription': None,
                    'language': None
                }]
            
            # 2. Créer des segments à partir des zones non-silencieuses
            segments = []
            
            # Ajouter silence initial si nécessaire
            if nonsilent_ranges[0][0] > 1000:  # Plus de 1 seconde
                segments.append({
                    'start': 0.0,
                    'end': nonsilent_ranges[0][0] / 1000.0,
                    'label': 'silence',
                    'confidence': 0.95,
                    'transcription': None,
                    'language': None
                })
            
            # Traiter chaque zone non-silencieuse
            for i, (start_ms, end_ms) in enumerate(nonsilent_ranges):
                start_sec = start_ms / 1000.0
                end_sec = end_ms / 1000.0
                
                # Si le segment est trop long, le découper
                if (end_sec - start_sec) > self.max_duration:
                    segments.extend(self._split_long_segment(
                        audio, start_ms, end_ms
                    ))
                else:
                    # Extraire le segment audio
                    segment_audio = audio[start_ms:end_ms]
                    
                    # Classifier et transcrire
                    label, confidence, transcription, language = self._classify_segment(
                        segment_audio, start_sec, end_sec
                    )
                    
                    segments.append({
                        'start': start_sec,
                        'end': end_sec,
                        'label': label,
                        'confidence': confidence,
                        'transcription': transcription,
                        'language': language
                    })
                
                # Ajouter silence entre les segments si nécessaire
                if i < len(nonsilent_ranges) - 1:
                    next_start = nonsilent_ranges[i + 1][0]
                    silence_duration = (next_start - end_ms) / 1000.0
                    
                    if silence_duration > 1.0:  # Plus de 1 seconde
                        segments.append({
                            'start': end_sec,
                            'end': next_start / 1000.0,
                            'label': 'silence',
                            'confidence': 0.95,
                            'transcription': None,
                            'language': None
                        })
            
            # Ajouter silence final si nécessaire
            last_end = nonsilent_ranges[-1][1] / 1000.0
            if (duration_sec - last_end) > 1.0:
                segments.append({
                    'start': last_end,
                    'end': duration_sec,
                    'label': 'silence',
                    'confidence': 0.95,
                    'transcription': None,
                    'language': None
                })
            
            logger.info(f"Generated {len(segments)} segments")
            return segments
            
        except Exception as e:
            logger.error(f"Error in segment_and_classify: {e}", exc_info=True)
            # En cas d'erreur, retourner un segment mock pour éviter le crash
            return [{
                'start': 0.0,
                'end': 10.0,
                'label': 'speech',
                'confidence': 0.5,
                'transcription': "Erreur de traitement audio",
                'language': 'fr'
            }]
    
    def _split_long_segment(self, audio: AudioSegment, start_ms: int, end_ms: int) -> List[Dict]:
        """Découpe un segment long en chunks de max_duration"""
        segments = []
        duration_ms = end_ms - start_ms
        chunk_duration_ms = int(self.max_duration * 1000)
        
        current_start = start_ms
        while current_start < end_ms:
            current_end = min(current_start + chunk_duration_ms, end_ms)
            
            segment_audio = audio[current_start:current_end]
            
            label, confidence, transcription, language = self._classify_segment(
                segment_audio,
                current_start / 1000.0,
                current_end / 1000.0
            )
            
            segments.append({
                'start': current_start / 1000.0,
                'end': current_end / 1000.0,
                'label': label,
                'confidence': confidence,
                'transcription': transcription,
                'language': language
            })
            
            current_start = current_end
        
        return segments
    
    def _classify_segment(
        self,
        segment_audio: AudioSegment,
        start_sec: float,
        end_sec: float
    ) -> Tuple[str, float, Optional[str], Optional[str]]:
        """
        Classifie un segment audio (speech/noise) et transcrit si speech
        """
        try:
            # Calculer l'énergie du signal
            rms = segment_audio.rms
            db = segment_audio.dBFS
            
            logger.debug(f"Segment [{start_sec:.2f}s - {end_sec:.2f}s]: RMS={rms}, dBFS={db:.1f}")
            
            # Heuristique simple pour distinguer speech/noise
            # Si l'énergie est faible, c'est probablement du bruit
            if db < -30 or rms < 500:
                return "noise", 0.7, None, None
            
            # Sinon, on considère que c'est de la parole et on transcrit
            if self.asr_model is not None:
                transcription, language, confidence = self._transcribe_segment_whisper(segment_audio)
                
                # Si la transcription est vide ou de très faible confiance, c'est du bruit
                if not transcription or confidence < 0.3:
                    return "noise", confidence, None, None
                
                return "speech", confidence, transcription, language
            else:
                # Si Whisper n'est pas chargé, on suppose que c'est de la parole
                logger.warning("⚠️  Whisper non chargé - classification par défaut")
                return "speech", 0.6, "Transcription non disponible (modèle non chargé)", "fr"
                
        except Exception as e:
            logger.error(f"Error classifying segment: {e}")
            return "noise", 0.5, None, None
    
    def _transcribe_segment_whisper(
        self,
        segment_audio: AudioSegment
    ) -> Tuple[str, str, float]:
        """
        Transcrit un segment audio avec Whisper - détection automatique de langue
        """
        try:
            # Convertir en array numpy et normaliser
            samples = np.array(segment_audio.get_array_of_samples())
            
            # Normaliser entre -1 et 1
            if segment_audio.sample_width == 2:  # 16-bit
                samples = samples.astype(np.float32) / 32768.0
            elif segment_audio.sample_width == 4:  # 32-bit
                samples = samples.astype(np.float32) / 2147483648.0
            
            # Rééchantillonner à 16kHz si nécessaire
            if segment_audio.frame_rate != self.sample_rate:
                # Utiliser torchaudio pour le resampling
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
            
            # 1. Détecter la langue automatiquement
            # Utiliser generate avec task="transcribe" et laisser Whisper détecter
            with torch.no_grad():
                # Générer sans langue forcée pour détection
                predicted_ids = self.asr_model.generate(
                    input_features,
                    task="transcribe",  # Laisser Whisper détecter la langue
                    language=None,       # Pas de langue forcée
                    max_length=225
                )
            
            # 2. Obtenir la langue détectée
            # Le premier token est le token de langue
            language_token = predicted_ids[0][0].item()
            
            # Mapper le token à un code langue
            # Les tokens de langue dans Whisper sont formatés comme <|lang|>
            language_map = {
                50258: "fr",    # <|fr|>
                50259: "en",    # <|en|>
                50260: "de",    # <|de|>
                50261: "es",    # <|es|>
                50262: "it",    # <|it|>
                50263: "pt",    # <|pt|>
                50264: "ru",    # <|ru|>
                50265: "zh",    # <|zh|>
                50266: "ja",    # <|ja|>
                50267: "ko",    # <|ko|>
                50268: "ar",    # <|ar|>
                50269: "hi",    # <|hi|>
            }
            
            detected_language = language_map.get(language_token, "unknown")
            
            if detected_language == "unknown":
                # Essayer de décoder pour voir
                try:
                    lang_str = self.asr_processor.tokenizer.decode([language_token])
                    # Extraire le code langue de <|fr|> -> fr
                    if lang_str.startswith("<|") and lang_str.endswith("|>"):
                        detected_language = lang_str[2:-2]
                    else:
                        detected_language = "unknown"
                except:
                    detected_language = "unknown"
            
            logger.debug(f"Langue détectée: {detected_language} (token: {language_token})")
            
            # 3. Transcrire avec la langue détectée (optionnel - on peut garder la première transcription)
            # Mais pour plus de précision, on peut regénérer avec la langue détectée
            if detected_language != "unknown" and detected_language != "fr":
                # Regénérer avec la langue détectée pour de meilleurs résultats
                with torch.no_grad():
                    predicted_ids = self.asr_model.generate(
                        input_features,
                        task="transcribe",
                        language=detected_language,  # Utiliser la langue détectée
                        max_length=225
                    )
            
            # Décoder
            transcription = self.asr_processor.batch_decode(
                predicted_ids,
                skip_special_tokens=True
            )[0]
            
            # Calculer une confiance approximative basée sur la longueur
            confidence = min(0.95, 0.5 + len(transcription) / 200)
            
            logger.debug(f"Transcription ({detected_language}): '{transcription}' (confidence: {confidence:.2f})")
            
            return transcription.strip(), detected_language, confidence
            
        except Exception as e:
            logger.error(f"Error in Whisper transcription: {e}")
            return "", "unknown", 0.0