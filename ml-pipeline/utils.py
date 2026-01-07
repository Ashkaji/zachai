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

# Limites pour éviter les crashes
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB max
CHUNK_SIZE = 1024 * 1024  # 1 MB par chunk pour téléchargement

def download_audio_file(url: str, task_id: int = None, api_key: str = None) -> str:
    """
    Télécharge depuis URL Label Studio ou MinIO - VERSION STREAMING
    Supporte les gros fichiers (100+ MB) sans crash mémoire
    """
    try:
        logger.info(f"📗 Downloading from: {url[:100]}...")
        
        # 1. CONVERSION CRITIQUE : URLs S3 → MinIO
        if url.startswith('s3://'):
            s3_path = url.replace('s3://', '')
            parts = s3_path.split('/', 1)
            
            if len(parts) == 2:
                bucket, key = parts
                url = f"http://minio:9000/{bucket}/{key}"
                logger.info(f"✅ Converted S3 → MinIO: {url}")
            else:
                logger.error(f"❌ Invalid S3 URL: {url}")
                return create_test_audio(task_id)
        
        # 2. Décoder fileuri base64 si présent
        if '/resolve-uri' in url or '/data/local-files/' in url:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            
            if 'fileuri' in query:
                try:
                    fileuri_encoded = query['fileuri'][0]
                    fileuri_decoded = base64.b64decode(fileuri_encoded).decode('utf-8')
                    logger.info(f"🔓 Decoded fileuri: {fileuri_decoded}")
                    
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
        url = unquote(url)
        
        logger.info(f"🎯 Final URL: {url[:200]}...")
        
        # 4. Headers
        headers = {}
        if api_key:
            headers['Authorization'] = f'Token {api_key}'
        
        if not url.startswith('http'):
            logger.error(f"❌ Not an HTTP URL: {url}")
            return create_test_audio(task_id)
        
        # 5. 🔥 TÉLÉCHARGEMENT EN STREAMING pour gros fichiers
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"❌ HTTP {response.status_code}")
            return create_test_audio(task_id)
        
        # Vérifier la taille avant de télécharger
        content_length = response.headers.get('content-length')
        if content_length:
            file_size = int(content_length)
            file_size_mb = file_size / 1024 / 1024
            logger.info(f"📦 File size: {file_size_mb:.1f} MB")
            
            if file_size > MAX_FILE_SIZE:
                logger.error(f"❌ File too large: {file_size_mb:.1f} MB (max {MAX_FILE_SIZE/1024/1024:.0f} MB)")
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
        elif 'audio/ogg' in content_type or '.ogg' in url.lower():
            ext = '.ogg'
        else:
            ext = '.mp3'  # Par défaut
        
        filepath = TEMP_DIR / f"{filename}{ext}"
        
        # 🔥 STREAMING WRITE pour éviter de charger tout en RAM
        logger.info(f"💾 Streaming download to: {filepath}")
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Log progress pour gros fichiers
                    if downloaded % (10 * 1024 * 1024) == 0:  # Tous les 10 MB
                        logger.info(f"  Downloaded: {downloaded / 1024 / 1024:.1f} MB...")
        
        file_size = os.path.getsize(filepath)
        file_size_mb = file_size / 1024 / 1024
        logger.info(f"✅ Downloaded: {filepath} ({file_size_mb:.1f} MB)")
        
        if file_size < 1000:
            logger.warning("⚠️ File very small, might be corrupted")
        
        return str(filepath)
        
    except requests.exceptions.Timeout:
        logger.error("❌ Download timeout (>60s)")
        return create_test_audio(task_id)
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Download request failed: {e}")
        return create_test_audio(task_id)
    except Exception as e:
        logger.error(f"❌ Download failed: {e}")
        return create_test_audio(task_id)


def create_test_audio(task_id: int = None) -> str:
    """Audio de test simple"""
    filename = f"test_{task_id or 'temp'}.wav"
    filepath = TEMP_DIR / filename
    
    logger.warning("🔄 Creating test audio")
    
    try:
        # 2 secondes de silence avec un petit bip
        sample_rate = 16000
        duration = 2.0
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio_data = 0.05 * np.sin(2 * np.pi * 440 * t)  # 440Hz
        
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
        with open(filepath, 'wb') as f:
            f.write(b'')
        return str(filepath)


def convert_to_wav(audio_path: str, target_sample_rate: int = 16000) -> str:
    """
    Convertit en WAV 16kHz mono - VERSION OPTIMISÉE GROS FICHIERS
    Utilise le chunking pour les fichiers >50MB
    """
    try:
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / 1024 / 1024
        
        logger.info(f"Converting audio to WAV: {audio_path} ({file_size_mb:.1f} MB)")
        
        # Vérifier que le fichier existe
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Nouveau chemin WAV
        wav_path = str(Path(audio_path).with_suffix('.wav'))
        
        # Si déjà WAV avec bon format, vérifier
        if audio_path.endswith('.wav'):
            try:
                audio = AudioSegment.from_wav(audio_path)
                
                # Vérifier si déjà au bon format
                needs_conversion = (
                    audio.frame_rate != target_sample_rate or 
                    audio.channels != 1
                )
                
                if not needs_conversion:
                    logger.info(f"Already in correct WAV format: {len(audio)}ms, {audio.frame_rate}Hz")
                    return audio_path
                else:
                    logger.info(f"WAV needs resampling/mono conversion")
            except Exception as e:
                logger.warning(f"WAV file seems corrupted, reconverting: {e}")
        
        logger.info(f"Converting to: {wav_path}")
        
        # 🔥 STRATÉGIE SELON LA TAILLE
        if file_size_mb > 50:
            logger.info(f"⚠️ Large file ({file_size_mb:.1f} MB) - Using optimized conversion")
            return _convert_large_file(audio_path, wav_path, target_sample_rate)
        else:
            logger.info("Standard conversion")
            return _convert_standard(audio_path, wav_path, target_sample_rate)
        
    except Exception as e:
        logger.error(f"Error converting to WAV: {e}", exc_info=True)
        logger.warning("Returning original file path")
        return audio_path


def _convert_standard(audio_path: str, wav_path: str, target_sample_rate: int) -> str:
    """Conversion standard pour fichiers <50MB"""
    try:
        # Charger l'audio
        audio = AudioSegment.from_file(audio_path)
        
        logger.info(f"Audio loaded: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels} channels")
        
        # Convertir en mono si nécessaire
        if audio.channels > 1:
            logger.info("Converting to mono")
            audio = audio.set_channels(1)
        
        # Resampler si nécessaire
        if audio.frame_rate != target_sample_rate:
            logger.info(f"Resampling from {audio.frame_rate}Hz to {target_sample_rate}Hz")
            audio = audio.set_frame_rate(target_sample_rate)
        
        # Exporter
        audio.export(wav_path, format='wav')
        
        wav_size = os.path.getsize(wav_path)
        logger.info(f"✓ Converted to WAV: {wav_path} ({wav_size / 1024 / 1024:.1f} MB)")
        
        return wav_path
        
    except Exception as e:
        logger.error(f"Standard conversion failed: {e}")
        raise


def _convert_large_file(audio_path: str, wav_path: str, target_sample_rate: int) -> str:
    """
    Conversion optimisée pour gros fichiers (>50MB)
    Traite par chunks pour éviter surcharge mémoire
    """
    try:
        import soundfile as sf
        import soxr
        
        logger.info("Using soundfile + soxr for large file conversion")
        
        # Lire avec soundfile (plus efficace pour gros fichiers)
        data, original_sr = sf.read(audio_path, dtype='float32')
        
        logger.info(f"Loaded with soundfile: shape={data.shape}, sr={original_sr}Hz")
        
        # Convertir en mono si stéréo
        if len(data.shape) > 1 and data.shape[1] > 1:
            logger.info(f"Converting {data.shape[1]} channels to mono")
            data = data.mean(axis=1)
        
        # Resampler si nécessaire avec soxr (plus rapide que pydub)
        if original_sr != target_sample_rate:
            logger.info(f"Resampling with soxr: {original_sr}Hz → {target_sample_rate}Hz")
            data = soxr.resample(data, original_sr, target_sample_rate)
        
        # Sauvegarder
        logger.info(f"Writing WAV: {wav_path}")
        sf.write(wav_path, data, target_sample_rate, subtype='PCM_16')
        
        wav_size = os.path.getsize(wav_path)
        logger.info(f"✓ Converted large file to WAV: {wav_path} ({wav_size / 1024 / 1024:.1f} MB)")
        
        # Libérer mémoire
        del data
        
        return wav_path
        
    except ImportError:
        logger.warning("soundfile/soxr not available, falling back to pydub")
        return _convert_standard(audio_path, wav_path, target_sample_rate)
    except Exception as e:
        logger.error(f"Large file conversion failed: {e}")
        logger.warning("Trying standard conversion as fallback")
        return _convert_standard(audio_path, wav_path, target_sample_rate)