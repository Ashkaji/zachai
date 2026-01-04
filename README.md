# 🎙️ Label Studio Audio Segmentation ML Backend

Backend ML automatique pour Label Studio permettant la segmentation et la classification audio (parole, bruit, silence) avec transcription multilingue via **Whisper**.

## 📋 Table des matières
- [Fonctionnalités](#fonctionnalités)
- [Démarrage rapide](#démarrage-rapide)
- [Architecture](#architecture)
- [Configuration complète](#configuration-complète)
- [Template Label Studio](#template-label-studio)
- [Vérification et débogage](#vérification-et-débogage)
- [Troubleshooting](#troubleshooting)
- [Personnalisation](#personnalisation)

## 🚀 Fonctionnalités

- ✅ **Segmentation automatique** basée sur la détection de silences
- ✅ **Classification** : parole (speech), bruit (noise), silence (silence)
- ✅ **Transcription automatique** des segments de parole avec **Whisper**
- ✅ **Détection de langue** : français (par défaut), anglais
- ✅ **Modèles open-source** pré-entraînés (Whisper Tiny)
- ✅ **Intégration complète** avec MinIO + Redis + Label Studio
- ✅ **Prédictions automatiques** directement dans l'interface

## ⚡ Démarrage rapide

### 1. **Construire et démarrer les services**

```bash
# Construire et démarrer tous les services
docker compose up --build -d

# Vérifier l'état des services
docker compose ps

# Tous les services doivent être "Up" et "healthy"
```

### 2. **Accéder aux interfaces**

| Service | URL | Identifiants | Usage |
|---------|-----|--------------|-------|
| **Label Studio** | http://localhost:8080 | Email: `admin@example.com`<br>Password: `admin123` | Interface d'annotation |
| **MinIO Console** | http://localhost:9001 | User: `minioadmin`<br>Password: `minioadmin123` | Stockage des fichiers audio |
| **ML Backend API** | http://localhost:9090 | - | API des prédictions |
| **Redis** | localhost:6379 | - | Queue des tâches |

### 3. **Vérifier la santé des services**

```bash
# Tester l'API ML Backend
curl http://localhost:9090/health
# Devrait retourner: {"status": "UP"}

# Tester MinIO
curl http://localhost:9000/minio/health/live

# Vérifier Redis
docker-compose exec redis redis-cli ping
# Devrait retourner: PONG
```

## 🏗️ Architecture

```
┌─────────────────┐
│  Label Studio   │
│    :8080        │
└────────┬────────┘
         │ 1. Demande prédiction
         ▼
┌─────────────────┐      ┌─────────────┐
│   ML Backend    │◄────►│    Redis    │
│     :9090       │      │    :6379    │
└────────┬────────┘      └─────────────┘
         │ 2. Télécharge audio
         ▼
┌─────────────────┐
│     MinIO       │
│  S3 Storage     │
│     :9000       │
└─────────────────┘

Workflow:
1. Utilisateur ouvre une tâche dans Label Studio
2. Label Studio appelle ML Backend pour les prédictions
3. ML Backend télécharge l'audio depuis MinIO
4. Traitement: Segmentation + Classification + Transcription
5. Retour des résultats à Label Studio
6. Affichage des pré-annotations
```

## 🔧 Configuration complète

### **Étape 1 : Créer un projet dans Label Studio**

1. Accédez à http://localhost:8080
2. Connectez-vous : `admin@example.com` / `admin123`
3. **Create Project** → Donnez un nom (ex: "Audio Segmentation")
4. Passez à l'étape suivante

### **Étape 2 : Configurer le template d'annotation**

Dans **Settings** → **Labeling Interface**, collez ce template :

```xml
<View>
  <Header value="Écouter et valider les segments audio"/>
  
  <!-- Lecteur audio avec contrôles -->
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true" hotkey="space"/>
  
  <!-- Labels pour classification -->
  <Labels name="label" toName="audio" choice="single" showInline="true">
    <Label value="speech" background="#4CAF50" hotkey="1"/>
    <Label value="noise" background="#FF9800" hotkey="2"/>
    <Label value="silence" background="#9E9E9E" hotkey="3"/>
  </Labels>
  
  <!-- Zone de transcription -->
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="3"
    maxSubmissions="0"
    showSubmitButton="false"
    placeholder="Transcription automatique (éditable)"/>
</View>
```

**Cliquez sur "Save"**

### **Étape 3 : Connecter le ML Backend**

1. Dans votre projet, allez dans **Settings** → **Machine Learning**
2. **Add Model** :
   - **URL** : `http://ml-backend:9090`
   - **Title** : `Audio Segmentation Model`
   - **Description** : `Segmentation et transcription automatique`
3. **Validate and Save**
   - ✅ Devrait afficher "Connected successfully"
   - ❌ Si erreur, consultez [Troubleshooting](#troubleshooting)

4. **Activer les prédictions automatiques** :
   - ☑️ Cochez "Use for interactive preannotations"
   - ☑️ Cochez "Retrieve predictions when loading a task"

### **Étape 4 : Importer des fichiers audio**

**Option A : Via MinIO (recommandé pour gros fichiers)**

```bash
# Copier vos fichiers audio vers MinIO
docker-compose exec minio mc cp /chemin/vers/votre-audio.mp3 myminio/labelstudio/

# Ou via l'interface web MinIO (http://localhost:9001)
# Bucket: labelstudio → Upload
```

Ensuite dans Label Studio :
1. **Settings** → **Cloud Storage** → **Add Source Storage**
2. **Storage Type** : Amazon S3
3. **Configuration** :
   - Storage Title : Un nom arbitraire
   - Bucket Name: `labelstudio`
   - Region Name: Laissez par défaut
   - S3 Endpoint: http://minio:9000
   - Access Key ID: minioadmin
   - Secret Access Key: minioadmin123
   - **Use pre-signed URLs** : ☐ **DÉCOCHER** (important!)
Dans "Import Settings & Preview", faites File Filter Regex: `.*\.(mp3|wav|m4a|ogg|flac)$`
4. **Add Storage** puis **Sync Storage**

**Option B : Upload direct (petit fichiers)**

1. Dans Label Studio, **Import**
2. **Upload Files** → Sélectionner vos fichiers audio
3. **Import**

### **Étape 5 : Obtenir les prédictions**

**Les prédictions se génèrent automatiquement** quand vous :
- Ouvrez une tâche pour la première fois
- Cliquez sur le bouton "Get predictions" dans l'interface

Vous devriez voir :
- 🟢 Des régions colorées sur la timeline audio
- 📝 Des transcriptions pour les segments de parole
- 🔢 Un score de confiance pour chaque prédiction

## 🔧 Personnalisation

### **Ajuster les seuils de segmentation**

```python
# Dans audio_segmenter.py, __init__
self.silence_thresh = -50    # Plus sensible (détecte plus de parole)
self.min_silence_len = 500   # Silence minimum plus long
```

### **Changer le modèle Whisper**

```python
# Dans audio_segmenter.py, load_models()
model_id = "openai/whisper-base"   # 74M params, meilleur compromis
# ou
model_id = "openai/whisper-small"  # 244M params, meilleure qualité
```

### **Ajouter des langues**

```python
# Dans audio_segmenter.py
self.languages = ["fr", "en", "es", "de"]  # Ajouter espagnol, allemand

# Le modèle détecte automatiquement, ou forcez dans _transcribe_segment_whisper
predicted_ids = self.asr_model.generate(
    input_features,
    language=None,  # Détection automatique
    max_length=225
)
```

### **Modifier les labels**

```python
# Dans model.py
self.labels = ["speech", "noise", "silence", "music", "background"]
```

Et mettez à jour le template XML en conséquence.

## 📊 Performance

**Temps de traitement typiques** (avec whisper-tiny sur CPU) :
- Audio de 1 minute : ~15-30 secondes
- Audio de 5 minutes : ~60-90 secondes
- Audio de 30 minutes : ~6-8 minutes

**Avec GPU (CUDA)** : environ 5-10x plus rapide

**Mémoire requise** :
- whisper-tiny : 2-4 GB RAM
- whisper-small : 4-6 GB RAM
- whisper-medium : 8-10 GB RAM

## 📁 Structure des fichiers

```
project/
├── compose.yml              # Configuration Docker Compose
├── ml-backend/
│   ├── Dockerfile          # Image Python avec dépendances ML
│   ├── requirements.txt    # Packages Python
│   ├── _wsgi.py           # Point d'entrée Flask
│   ├── model.py           # Modèle Label Studio ML
│   ├── audio_segmenter.py # Logique de segmentation
│   └── utils.py           # Utilitaires (download, convert)
└── README.md              # Ce fichier
```

## 🔮 Roadmap

- [x] Segmentation basique
- [x] Classification speech/noise/silence
- [x] Transcription avec Whisper
- [x] Intégration Label Studio + MinIO
- [ ] Support GPU pour accélération
- [ ] Diarization (identification des locuteurs)
- [ ] Détection d'émotions
- [ ] Support de plus de langues
- [ ] Batch processing asynchrone
- [ ] Interface de monitoring

## 📄 License

Open-source - Utilisation libre

## ❓ Support

**En cas de problème** :

1. Consultez les logs : `docker-compose logs -f ml-backend`
2. Lancez le script de vérification : `./check_setup.sh`
3. Vérifiez cette section de troubleshooting
4. Testez manuellement l'API : `curl http://localhost:9090/predict`

**Les logs du ML Backend sont très verbeux** et vous diront exactement où le problème se situe.

---


**Note** : Au premier démarrage, le ML Backend télécharge automatiquement le modèle Whisper (~150 MB pour whisper-tiny). Cette opération prend 2-5 minutes selon votre connexion Internet.


