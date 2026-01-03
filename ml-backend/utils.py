import os
import requests
import logging
import base64
import numpy as np
from pathlib import Path
from pydub import AudioSegment
from urllib.parse import urlparse, parse_qs, unquote

logger = logging.getLogger(__name__)

TEMP_DIR = Path("/tmp/label_studio_audio")
TEMP_DIR.mkdir(exist_ok=True)

def download_audio_file(url: str, task_id: int = None, api_key: str = None) -> str:
    """
    Télécharge depuis URL Label Studio ou MinIO - VERSION SIMPLIFIÉE
    """
    try:
        logger.info(f"🔗 Downloading from: {url[:100]}...")
        
        # 1. CONVERSION CRITIQUE : URLs S3 → MinIO
        if url.startswith('s3://'):
            # Format: s3://bucket/key
            s3_path = url.replace('s3://', '')
            parts = s3_path.split('/', 1)
            
            if len(parts) == 2:
                bucket, key = parts
                url = f"http://minio:9000/{bucket}/{key}"
                logger.info(f"✅ Converted S3 → MinIO: {url}")
            else:
                logger.error(f"❌ Invalid S3 URL: {url}")
                return create_test_audio(task_id)
        
        # 2. Décoder fileuri base64 si présent (URLs proxy Label Studio)
        if '/resolve-uri' in url or '/data/local-files/' in url:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            
            if 'fileuri' in query:
                try:
                    fileuri_encoded = query['fileuri'][0]
                    fileuri_decoded = base64.b64decode(fileuri_encoded).decode('utf-8')
                    logger.info(f"🔓 Decoded fileuri: {fileuri_decoded}")
                    
                    # Si c'est S3, convertir
                    if fileuri_decoded.startswith('s3://'):
                        s3_path = fileuri_decoded.replace('s3://', '')
                        parts = s3_path.split('/', 1)
                        if len(parts) == 2:
                            bucket, key = parts
                            url = f"http://minio:9000/{bucket}/{key}"
                            logger.info(f"✅ Converted decoded S3 → MinIO: {url}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not decode fileuri: {e}")
        
        # 3. URL interne Docker
        url = url.replace('localhost:9000', 'minio:9000')
        url = url.replace('localhost:8080', 'labelstudio:8080')
        
        # Décoder les caractères spéciaux
        url = unquote(url)
        
        logger.info(f"🎯 Final URL: {url[:200]}...")
        
        # 4. Télécharger (sans API key si None)
        headers = {}
        if api_key:
            headers['Authorization'] = f'Token {api_key}'
        else:
            logger.debug("No API key provided, downloading without auth")
        
        # Vérifier que c'est HTTP
        if not url.startswith('http'):
            logger.error(f"❌ Not an HTTP URL: {url}")
            return create_test_audio(task_id)
        
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"❌ HTTP {response.status_code}")
            return create_test_audio(task_id)
        
        # Déterminer le nom de fichier
        filename = f"audio_{task_id or 'temp'}"
        
        # Deviner l'extension
        content_type = response.headers.get('content-type', '')
        if 'audio/mpeg' in content_type or '.mp3' in url.lower():
            ext = '.mp3'
        elif 'audio/wav' in content_type or '.wav' in url.lower():
            ext = '.wav'
        elif 'audio/mp4' in content_type or '.m4a' in url.lower():
            ext = '.m4a'
        else:
            # Par défaut mp3
            ext = '.mp3'
        
        filepath = TEMP_DIR / f"{filename}{ext}"
        
        # Sauvegarder
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        file_size = os.path.getsize(filepath)
        logger.info(f"✅ Downloaded: {filepath} ({file_size} bytes)")
        
        if file_size < 1000:
            logger.warning("⚠️ File very small, might be corrupted")
        
        return str(filepath)
        
    except Exception as e:
        logger.error(f"❌ Download failed: {e}")
        return create_test_audio(task_id)

def create_test_audio(task_id: int = None) -> str:
    """Audio de test simple"""
    import numpy as np
    
    filename = f"test_{task_id or 'temp'}.wav"
    filepath = TEMP_DIR / filename
    
    logger.warning("🔄 Creating test audio")
    
    try:
        # 2 secondes de silence avec un petit bip
        sample_rate = 16000
        duration = 2.0
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio_data = 0.05 * np.sin(2 * np.pi * 440 * t)  # 440Hz
        
        # Convertir
        audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
        
        audio = AudioSegment(
            audio_bytes,
            frame_rate=sample_rate,
            sample_width=2,
            channels=1
        )
        
        audio.export(filepath, format="wav")
        return str(filepath)
        
    except Exception as e:
        logger.error(f"❌ Failed test audio: {e}")
        # Fichier vide comme dernier recours
        with open(filepath, 'wb') as f:
            f.write(b'')
        return str(filepath)

def convert_to_wav(audio_path: str) -> str:
    """Convertit en WAV si nécessaire - version robuste"""
    try:
        logger.info(f"Converting audio to WAV: {audio_path}")
        
        # Vérifier que le fichier existe
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Si déjà en WAV, vérifier qu'il est valide
        if audio_path.endswith('.wav'):
            try:
                # Essayer de charger pour valider
                audio = AudioSegment.from_wav(audio_path)
                logger.info(f"Already in WAV format: {len(audio)}ms, {audio.frame_rate}Hz")
                return audio_path
            except Exception as e:
                logger.warning(f"WAV file seems corrupted, reconverting: {e}")
        
        # Déterminer le nouveau chemin
        wav_path = str(Path(audio_path).with_suffix('.wav'))
        
        logger.info(f"Converting to: {wav_path}")
        
        # Charger l'audio (pydub devine automatiquement le format)
        try:
            audio = AudioSegment.from_file(audio_path)
        except Exception as e:
            logger.warning(f"Failed to auto-detect format, trying explicit formats: {e}")
            
            # Essayer explicitement différents formats
            for fmt in ['mp3', 'mp4', 'm4a', 'ogg', 'flac', 'wav']:
                try:
                    audio = AudioSegment.from_file(audio_path, format=fmt)
                    logger.info(f"Successfully loaded as {fmt}")
                    break
                except:
                    continue
            else:
                raise ValueError(f"Could not load audio file in any known format")
        
        logger.info(f"Audio loaded: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels} channels")
        
        # Convertir en mono 16kHz si nécessaire (optimal pour Whisper)
        if audio.channels > 1:
            logger.info("Converting to mono")
            audio = audio.set_channels(1)
        
        if audio.frame_rate != 16000:
            logger.info(f"Resampling from {audio.frame_rate}Hz to 16000Hz")
            audio = audio.set_frame_rate(16000)
        
        # Exporter en WAV
        audio.export(wav_path, format='wav')
        
        wav_size = os.path.getsize(wav_path)
        logger.info(f"✓ Converted to WAV: {wav_path} ({wav_size} bytes)")
        
        return wav_path
        
    except Exception as e:
        logger.error(f"Error converting to WAV: {e}", exc_info=True)
        
        logger.warning("Returning original file path")
        return audio_path
    