#!/usr/bin/env python3
"""
Script pour pré-télécharger tous les modèles nécessaires pendant le build Docker.
VERSION ULTRA-ROBUSTE - Ne peut pas échouer silencieusement
"""
import os
import sys
import logging
from pathlib import Path

# Configuration du logging AVANT tout
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s | %(message)s',
    stream=sys.stdout  # Forcer stdout pour voir dans les logs Docker
)
logger = logging.getLogger(__name__)

# Forcer les prints à s'afficher immédiatement
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def print_banner(text):
    """Affiche un banner visible"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")
    sys.stdout.flush()

def download_whisper_model():
    """Télécharge le modèle Whisper - VERSION ULTRA-ROBUSTE"""
    print_banner("📥 DÉBUT DU TÉLÉCHARGEMENT DE WHISPER TINY")
    
    try:
        # Import APRÈS avoir configuré le logging
        print("⏳ Import des librairies transformers...")
        sys.stdout.flush()
        
        from transformers import WhisperProcessor, WhisperForConditionalGeneration
        print("✅ Librairies importées avec succès")
        sys.stdout.flush()
        
        model_id = "openai/whisper-tiny"
        model_dir = "/app/models/whisper-tiny"
        
        # Créer le dossier
        print(f"\n📁 Création du dossier: {model_dir}")
        Path(model_dir).mkdir(parents=True, exist_ok=True)
        print(f"✅ Dossier créé: {model_dir}")
        sys.stdout.flush()
        
        print(f"\n🌐 Modèle source: {model_id}")
        print(f"📍 Destination: {model_dir}")
        sys.stdout.flush()
        
        # ÉTAPE 1: Télécharger le processeur
        print("\n" + "-" * 80)
        print("⏳ [1/2] TÉLÉCHARGEMENT DU PROCESSOR")
        print("-" * 80)
        sys.stdout.flush()
        
        processor = WhisperProcessor.from_pretrained(
            model_id,
            cache_dir=None,  # Laisser HF gérer le cache
        )
        print("✅ Processor téléchargé depuis HuggingFace")
        sys.stdout.flush()
        
        # Sauvegarder explicitement
        print(f"💾 Sauvegarde dans {model_dir}...")
        sys.stdout.flush()
        
        processor.save_pretrained(model_dir)
        print("✅ Processor sauvegardé localement")
        sys.stdout.flush()
        
        # ÉTAPE 2: Télécharger le modèle
        print("\n" + "-" * 80)
        print("⏳ [2/2] TÉLÉCHARGEMENT DU MODEL (~150 MB)")
        print("    Ceci peut prendre 1-3 minutes selon votre connexion...")
        print("-" * 80)
        sys.stdout.flush()
        
        model = WhisperForConditionalGeneration.from_pretrained(
            model_id,
            cache_dir=None,
        )
        print("✅ Model téléchargé depuis HuggingFace")
        sys.stdout.flush()
        
        # Sauvegarder explicitement
        print(f"💾 Sauvegarde dans {model_dir}...")
        sys.stdout.flush()
        
        model.save_pretrained(model_dir)
        print("✅ Model sauvegardé localement")
        sys.stdout.flush()
        
        # VÉRIFICATION DÉTAILLÉE
        print_banner("🔍 VÉRIFICATION DES FICHIERS")
        
        if not os.path.exists(model_dir):
            print(f"❌ ERREUR CRITIQUE: Le dossier {model_dir} n'existe pas!")
            return False
        
        files = sorted(Path(model_dir).rglob('*'))
        file_list = [f for f in files if f.is_file()]
        
        if not file_list:
            print(f"❌ ERREUR CRITIQUE: Aucun fichier dans {model_dir}!")
            return False
        
        total_size = sum(f.stat().st_size for f in file_list)
        total_size_mb = total_size / 1024 / 1024
        
        print(f"📊 Statistiques:")
        print(f"   • Nombre de fichiers: {len(file_list)}")
        print(f"   • Taille totale: {total_size_mb:.1f} MB")
        print("")
        sys.stdout.flush()
        
        # Vérifier les fichiers critiques
        print("📝 Fichiers critiques:")
        critical_files = {
            'config.json': False,
            'preprocessor_config.json': False,
            'tokenizer_config.json': False,
            'vocab.json': False,
        }
        
        model_file_found = False
        
        for file_path in file_list:
            filename = file_path.name
            
            # Vérifier les fichiers critiques
            if filename in critical_files:
                critical_files[filename] = True
                size_kb = file_path.stat().st_size / 1024
                print(f"   ✅ {filename:<35} ({size_kb:>8.1f} KB)")
            
            # Vérifier le fichier du modèle (le plus gros)
            if filename.endswith('.bin') or filename.endswith('.safetensors'):
                model_file_found = True
                size_mb = file_path.stat().st_size / 1024 / 1024
                print(f"   ✅ {filename:<35} ({size_mb:>8.1f} MB) ⭐")
        
        sys.stdout.flush()
        
        # Vérifier qu'on a tout
        print("")
        missing_files = [name for name, found in critical_files.items() if not found]
        
        if missing_files:
            print(f"❌ ERREUR: Fichiers manquants: {', '.join(missing_files)}")
            return False
        
        if not model_file_found:
            print("❌ ERREUR: Fichier du modèle (.bin ou .safetensors) introuvable!")
            return False
        
        if total_size_mb < 50:
            print(f"❌ ERREUR: Taille totale trop petite ({total_size_mb:.1f} MB)")
            print("   Le modèle Whisper tiny devrait faire ~150 MB minimum")
            return False
        
        print_banner("✅ ✅ ✅  SUCCÈS TOTAL  ✅ ✅ ✅")
        print(f"Le modèle Whisper tiny a été téléchargé avec succès!")
        print(f"Emplacement: {model_dir}")
        print(f"Taille: {total_size_mb:.1f} MB")
        print("")
        
        return True
        
    except ImportError as e:
        print_banner("❌ ERREUR D'IMPORT")
        print(f"Impossible d'importer transformers: {e}")
        print("")
        print("💡 Solution: Vérifier que transformers est bien installé")
        print("   pip install transformers")
        return False
        
    except Exception as e:
        print_banner("❌ ERREUR INATTENDUE")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        print("")
        
        # Afficher la traceback complète
        import traceback
        print("Traceback complet:")
        traceback.print_exc()
        
        return False

def main():
    """Fonction principale"""
    print("")
    print("=" * 80)
    print("  🚀 SCRIPT DE TÉLÉCHARGEMENT DES MODÈLES")
    print("=" * 80)
    print("")
    
    # Afficher la configuration
    print("📋 Configuration:")
    print(f"   • Python: {sys.version.split()[0]}")
    print(f"   • Working dir: {os.getcwd()}")
    print(f"   • TRANSFORMERS_CACHE: {os.environ.get('TRANSFORMERS_CACHE', 'non défini')}")
    print(f"   • HF_HOME: {os.environ.get('HF_HOME', 'non défini')}")
    print("")
    sys.stdout.flush()
    
    # Télécharger
    success = download_whisper_model()
    
    print("")
    if success:
        print("=" * 80)
        print("  ✅ ✅ ✅  TÉLÉCHARGEMENT TERMINÉ AVEC SUCCÈS  ✅ ✅ ✅")
        print("=" * 80)
        print("")
        sys.exit(0)
    else:
        print("=" * 80)
        print("  ❌ ❌ ❌  ÉCHEC DU TÉLÉCHARGEMENT  ❌ ❌ ❌")
        print("=" * 80)
        print("")
        print("🔍 Debug: Contenu de /app/models/")
        try:
            for item in os.listdir("/app/models"):
                path = os.path.join("/app/models", item)
                if os.path.isdir(path):
                    print(f"   📁 {item}/")
                else:
                    size = os.path.getsize(path) / 1024
                    print(f"   📄 {item} ({size:.1f} KB)")
        except Exception as e:
            print(f"   Erreur: {e}")
        print("")
        sys.exit(1)

if __name__ == "__main__":
    main()