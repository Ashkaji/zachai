# 🎙️ Label Studio Audio Segmentation ML Backend

Backend ML automatique pour Label Studio permettant la **détection et transcription des zones de parole** dans les fichiers audio, avec support des **gros fichiers (100MB+)**.

## 🚀 Fonctionnalités

- ✅ **Détection automatique des zones de parole** (speech detection)
- ✅ **Transcription multilingue** avec Whisper (français, anglais, espagnol, etc.)
- ✅ **Support des gros fichiers** : traitement en streaming pour audios de 100MB à plusieurs GB
- ✅ **Pas d'attente** : le traitement commence immédiatement, segment par segment
- ✅ **Détection automatique de langue** pour chaque segment
- ✅ **Templates adaptables** : configurez selon votre projet (témoignages, enseignements, campagnes, etc.)
- ✅ **Modèles open-source** pré-entraînés (Whisper Tiny)
- ✅ **Intégration complète** avec MinIO + Redis + Label Studio

## 📋 Table des matières
- [Démarrage rapide](#démarrage-rapide)
- [Architecture](#architecture)
- [Configuration complète](#configuration-complète)
- [Templates d'annotation](#templates-dannotation)
- [Utilisation](#utilisation)
- [Performance](#performance)
- [Personnalisation](#personnalisation)
- [Troubleshooting](#troubleshooting)

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
4. Traitement STREAMING: Segmentation + Transcription progressive
5. Retour des résultats à Label Studio (zones de parole + transcriptions)
6. Affichage des pré-annotations avec labels à valider/modifier
```

## 🔧 Configuration complète

### **Étape 1 : Créer un projet dans Label Studio**

1. Accédez à http://localhost:8080
2. Connectez-vous : `admin@example.com` / `admin123`
3. **Create Project** → Donnez un nom selon votre projet (ex: "Témoignage Conversion", "Camp Biblique 2024")
4. Passez à l'étape suivante

### **Étape 2 : Configurer le template d'annotation**

Dans **Settings** → **Labeling Interface**, choisissez et collez le template adapté à votre projet :

#### 🎯 Template Simple - Sans labels prédéfinis (Recommandé pour débuter)

**Utilisation** : Les régions de parole sont détectées automatiquement SANS label. Vous cliquez sur une région pour lui ajouter le label de votre choix.

```xml
<View>
  <Header value="Annotation audio - Cliquez sur une région pour ajouter un label"/>
  
  <!-- Lecteur audio avec contrôles -->
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true" hotkey="space"/>
  
  <!-- Labels pour classification (à ajouter manuellement) -->
  <Labels name="label" toName="audio" choice="single" showInline="true" maxSubmissions="1">
    <Label value="speech" background="#4CAF50" hotkey="1"/>
    <Label value="noise" background="#2196F3" hotkey="2"/>
    <Label value="silence" background="#9E9E9E" hotkey="3"/>
  </Labels>
  
  <!-- Zone de transcription -->
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="3"
    maxSubmissions="1"
    placeholder="Transcription automatique (éditable)"/>
</View>
```

**Workflow** :
1. Le système détecte automatiquement les zones de parole (régions **SANS label**)
2. Vous écoutez chaque région
3. Vous **cliquez sur la région** et choisissez le label approprié
4. Vous éditez la transcription si besoin

**Avantage** : Maximum de flexibilité - vous définissez vos labels selon chaque projet

---

#### ✝️ Template : Témoignage de Conversion

**Utilisation** : Enregistrements d'interviews de témoignages chrétiens

```xml
<View>
  <Header value="Annotation de témoignage - Identifier les intervenants"/>
  
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true" hotkey="space"/>
  
  <!-- Labels pour les intervenants et moments -->
  <Labels name="label" toName="audio" choice="single" showInline="true" maxSubmissions="1">
    <Label value="présentation" background="#E3F2FD" hotkey="1"/>
    <Label value="interviewer" background="#4CAF50" hotkey="2"/>
    <Label value="répondant" background="#2196F3" hotkey="3"/>
    <Label value="pause" background="#FFF9C4" hotkey="4"/>
    <Label value="rires" background="#FFE082" hotkey="5"/>
    <Label value="bruits" background="#BDBDBD" hotkey="6"/>
  </Labels>
  
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="4"
    maxSubmissions="1"
    placeholder="Transcription du témoignage"/>
  
  <Text value="💡 Raccourcis : 1=Présentation | 2=Interviewer | 3=Répondant | 4=Pause | 5=Rires | 6=Bruits"/>
</View>
```

---

#### ⛺ Template : Camp Biblique

**Utilisation** : Enregistrements de camps, retraites, conventions

```xml
<View>
  <Header value="Annotation de camp biblique"/>
  
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true" hotkey="space"/>
  
  <Labels name="label" toName="audio" choice="single" showInline="true" maxSubmissions="1">
    <Label value="orateur" background="#1976D2" hotkey="1"/>
    <Label value="traducteur" background="#0097A7" hotkey="2"/>
    <Label value="prières" background="#7B1FA2" hotkey="3"/>
    <Label value="louanges" background="#F57C00" hotkey="4"/>
    <Label value="verset_biblique" background="#388E3C" hotkey="5"/>
    <Label value="silence" background="#9E9E9E" hotkey="6"/>
  </Labels>
  
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="4"
    maxSubmissions="1"
    placeholder="Transcription (parole, chant, verset...)"/>
  
  <Text value="💡 1=Orateur | 2=Traducteur | 3=Prières | 4=Louanges | 5=Verset | 6=Silence"/>
</View>
```

---

#### 📖 Template : Enseignement Biblique

**Utilisation** : Prédications, études bibliques, séminaires

```xml
<View>
  <Header value="Annotation d'enseignement biblique"/>
  
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true" hotkey="space"/>
  
  <Labels name="label" toName="audio" choice="single" showInline="true" maxSubmissions="1">
    <Label value="orateur" background="#1565C0" hotkey="1"/>
    <Label value="traducteur" background="#00838F" hotkey="2"/>
    <Label value="verset_biblique" background="#2E7D32" hotkey="3"/>
    <Label value="silence" background="#9E9E9E" hotkey="4"/>
  </Labels>
  
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="4"
    maxSubmissions="1"
    placeholder="Transcription de l'enseignement"/>
  
  <!-- Champ supplémentaire pour références bibliques -->
  <TextArea
    name="references"
    toName="audio"
    editable="true"
    rows="2"
    maxSubmissions="1"
    placeholder="Références bibliques (ex: Jean 3:16, Romains 8:28)"/>
  
  <Text value="💡 1=Orateur | 2=Traducteur | 3=Verset | 4=Silence"/>
</View>
```

---

#### 🔥 Template : Campagne d'Évangélisation

**Utilisation** : Crusades, campagnes d'évangélisation, événements de masse

```xml
<View>
  <Header value="Annotation de campagne d'évangélisation"/>
  
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true" hotkey="space"/>
  
  <Labels name="label" toName="audio" choice="single" showInline="true" maxSubmissions="1">
    <Label value="orateur" background="#C62828" hotkey="1"/>
    <Label value="traducteur" background="#AD1457" hotkey="2"/>
    <Label value="prières" background="#6A1B9A" hotkey="3"/>
    <Label value="délivrances" background="#4527A0" hotkey="4"/>
    <Label value="louanges" background="#EF6C00" hotkey="5"/>
    <Label value="appel" background="#D84315" hotkey="6"/>
    <Label value="verset_biblique" background="#2E7D32" hotkey="7"/>
    <Label value="silence" background="#9E9E9E" hotkey="8"/>
  </Labels>
  
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="4"
    maxSubmissions="1"
    placeholder="Transcription"/>
  
  <Text value="💡 1=Orateur | 2=Traducteur | 3=Prières | 4=Délivrances | 5=Louanges | 6=Appel | 7=Verset | 8=Silence"/>
</View>
```

---

#### 🎤 Template : Podcast / Interview

**Utilisation** : Podcasts, interviews, discussions

```xml
<View>
  <Header value="Annotation de podcast / interview"/>
  
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true" hotkey="space"/>
  
  <Labels name="label" toName="audio" choice="single" showInline="true" maxSubmissions="1">
    <Label value="hôte" background="#1976D2" hotkey="1"/>
    <Label value="invité_1" background="#388E3C" hotkey="2"/>
    <Label value="invité_2" background="#F57C00" hotkey="3"/>
    <Label value="intro" background="#7B1FA2" hotkey="4"/>
    <Label value="outro" background="#C2185B" hotkey="5"/>
    <Label value="publicité" background="#FBC02D" hotkey="6"/>
    <Label value="silence" background="#9E9E9E" hotkey="7"/>
  </Labels>
  
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="4"
    maxSubmissions="1"
    placeholder="Transcription"/>
  
  <Text value="💡 1=Hôte | 2=Invité 1 | 3=Invité 2 | 4=Intro | 5=Outro | 6=Pub | 7=Silence"/>
</View>
```

---

**💡 Conseil** : Commencez avec le **template standard** pour vous familiariser, puis créez votre template personnalisé selon vos besoins spécifiques.

**Cliquez sur "Save"** après avoir collé votre template

---

### **Étape 3 : Connecter le ML Backend**

1. Dans votre projet, allez dans **Settings** → **Machine Learning**
2. **Add Model** :
   - **URL** : `http://ml-backend:9090`
   - **Title** : `Audio Speech Detection`
   - **Description** : `Détection automatique des zones de parole + transcription`
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
   - S3 Endpoint: `http://minio:9000`
   - Access Key ID: `minioadmin`
   - Secret Access Key: `minioadmin123`
   - **Use pre-signed URLs** : ☐ **DÉCOCHER** (important!)
   - Dans "Import Settings & Preview", File Filter Regex: `.*\.(mp3|wav|m4a|ogg|flac)$`
4. **Add Storage** puis **Sync Storage**

**Option B : Upload direct (petits fichiers)**

1. Dans Label Studio, **Import**
2. **Upload Files** → Sélectionner vos fichiers audio
3. **Import**

### **Étape 5 : Obtenir les prédictions**

**Les prédictions se génèrent automatiquement** quand vous :
- Ouvrez une tâche pour la première fois
- Cliquez sur le bouton "Get predictions" dans l'interface

Vous devriez voir :
- 🔘 Des régions **grises** sur la timeline audio (zones de parole détectées **SANS label**)
- 📝 Des transcriptions pour chaque région
- 🔢 Un score de confiance pour chaque prédiction
- 👆 Possibilité de **cliquer sur une région** pour lui ajouter un label

## 🎯 Utilisation

### Workflow d'annotation

1. **Ouvrir une tâche** dans Label Studio
2. **Attendre les prédictions** (quelques secondes à quelques minutes selon la taille)
3. **Voir les régions grises** détectées automatiquement sur la timeline
4. **Cliquer sur une région** pour lui ajouter un label selon votre projet
   - Ex: "orateur", "traducteur", "prières", "louanges", etc.
5. **Éditer la transcription** si nécessaire (cliquez dans le champ texte)
6. **Submit** pour sauvegarder vos annotations

### Comprendre les régions

- **Régions grises (sans label)** : Zones de parole détectées automatiquement
- **Score de confiance** : Affiché sur chaque région (0.0 à 1.0)
- **Transcription** : Texte automatiquement généré, éditable à tout moment
- **Labels** : À ajouter manuellement en cliquant sur la région

### Exemples de projets réels

#### 📖 Projet : Archivage de prédications

**Objectif** : Créer une base de données de prédications avec transcriptions

**Template** : Enseignement Biblique

**Workflow** :
1. Upload des audios de prédications dans MinIO
2. Annotation automatique (zones de parole + transcriptions)
3. Validation et ajout des références bibliques
4. Export en JSON avec timestamps

#### ⛺ Projet : Documentation de camp de jeunes

**Objectif** : Documenter les moments clés d'un camp

**Template** : Camp Biblique

**Workflow** :
1. Upload des enregistrements quotidiens
2. Classification automatique des segments
3. Identification des louanges, prières, enseignements
4. Création d'un catalogue avec timestamps

#### 🔥 Projet : Archive de campagne d'évangélisation

**Objectif** : Préserver les moments forts d'une crusade

**Template** : Campagne d'Évangélisation

**Workflow** :
1. Upload des enregistrements de chaque jour
2. Détection des moments clés (appels, délivrances, témoignages)
3. Transcription des prières et déclarations
4. Export pour diffusion

## 📊 Performance

### Temps de traitement typiques

**Avec whisper-tiny sur CPU** :
- Audio de 1 minute : ~15-30 secondes
- Audio de 5 minutes : ~60-90 secondes
- Audio de 30 minutes : ~6-8 minutes
- Audio de 2 heures : ~20-30 minutes

**Avec GPU (CUDA)** : environ 5-10x plus rapide

### Mémoire requise

**Par le ML Backend** :
- whisper-tiny : 2-4 GB RAM
- whisper-small : 4-6 GB RAM
- whisper-medium : 8-10 GB RAM

**Support des gros fichiers** :
- ✅ Audios jusqu'à 200 MB : sans problème
- ✅ Audios jusqu'à 1 GB : traitement en streaming
- ✅ Audios > 1 GB : possibles, mais lents (prévoir 1-2h de traitement)

### Limitations actuelles

- **Taille max par upload** : 200 MB (configurable dans compose.yml)
- **Timeout de prédiction** : 30 minutes par audio
- **Langues supportées** : Détection automatique parmi 12+ langues

## 🔧 Personnalisation

### Ajuster les seuils de détection de parole

```python
# Dans audio_segmenter.py, __init__
self.silence_thresh = -35      # Plus sensible = détecte plus de parole
self.min_silence_len = 400     # Durée minimum du silence (ms)
self.min_speech_duration = 0.5 # Durée minimum d'un segment (secondes)
```

### Changer le modèle Whisper

```python
# Dans download_models.py et audio_segmenter.py
model_id = "openai/whisper-base"   # 74M params, meilleur compromis
# ou
model_id = "openai/whisper-small"  # 244M params, meilleure qualité
# ou
model_id = "openai/whisper-medium" # 769M params, qualité maximale (lent)
```

### Forcer une langue spécifique

```python
# Dans audio_segmenter.py, _transcribe_segment_whisper
predicted_ids = self.asr_model.generate(
    input_features,
    task="transcribe",
    language="fr",  # Forcer le français au lieu de None (détection auto)
    max_length=225
)
```

### Créer votre propre template

**Structure de base** :

```xml
<View>
  <Header value="Titre de votre projet"/>
  
  <Audio name="audio" value="$audio" zoom="true" speed="true" volume="true"/>
  
  <Labels name="label" toName="audio" choice="single" showInline="true" maxSubmissions="1">
    <!-- Ajoutez vos labels personnalisés -->
    <Label value="mon_label_1" background="#COULEUR" hotkey="1"/>
    <Label value="mon_label_2" background="#COULEUR" hotkey="2"/>
    <!-- etc. -->
  </Labels>
  
  <TextArea 
    name="transcription" 
    toName="audio" 
    editable="true" 
    rows="3"
    maxSubmissions="1"
    placeholder="Votre placeholder"/>
</View>
```

**Conseils** :
- Utilisez des couleurs distinctes pour chaque label
- Assignez des hotkeys (1-9) pour l'annotation rapide
- Limitez-vous à 6-8 labels pour la lisibilité
- Choisissez des noms de labels clairs et courts
- Ajoutez toujours `maxSubmissions="1"` sur Labels et TextArea

### Augmenter les limites mémoire

```yaml
# Dans compose.yml, service ml-backend
mem_limit: 16g        # 16 GB au lieu de 8 GB
mem_reservation: 8g   # 8 GB au lieu de 4 GB
```

## ❓ Troubleshooting

### Le ML Backend ne se connecte pas

```bash
# Vérifier les logs
docker-compose logs -f ml-backend

# Cherchez :
# ✅ "Modèle Whisper chargé avec succès!"
# ❌ "ERREUR lors du chargement des modèles"
```

**Solution** : Rebuilder avec `docker-compose build --no-cache ml-backend`

### Les prédictions sont vides

**Causes possibles** :
1. L'audio est trop silencieux → Ajuster `silence_thresh` dans `audio_segmenter.py`
2. Pas de parole détectée → Vérifier que l'audio contient bien de la parole
3. Modèles non chargés → Vérifier les logs du ML Backend

### Timeout pour gros fichiers

**Solution** : Augmenter les timeouts dans `compose.yml` :

```yaml
# Dans labelstudio service
- LABEL_STUDIO_ML_TIMEOUT=3600  # 60 minutes au lieu de 30

# Dans ml-backend service
- PREDICTION_TIMEOUT=3600  # 60 minutes
```

### Erreur "File too large"

**Solution 1** : Augmenter la limite d'upload

```yaml
# Dans compose.yml, labelstudio service
- LABEL_STUDIO_MAX_UPLOAD_SIZE=524288000  # 500 MB
- NGINX_CLIENT_MAX_BODY_SIZE=500m
```

**Solution 2** : Utiliser MinIO au lieu de l'upload direct (voir Étape 4)

### Mémoire insuffisante

```bash
# Monitorer la mémoire
docker stats ml-backend

# Si proche de la limite :
# 1. Augmenter mem_limit dans compose.yml
# 2. Ou utiliser un modèle plus petit (whisper-tiny au lieu de base)
```

### Les transcriptions sont dans la mauvaise langue

**Solution** : Forcer la langue dans `audio_segmenter.py`

```python
# Dans _transcribe_segment_whisper, ligne ~285
predicted_ids = self.asr_model.generate(
    input_features,
    task="transcribe",
    language="fr",  # Forcer français (ou "en", "es", etc.)
    max_length=225
)
```

## 📁 Structure des fichiers

```
project/
├── compose.yml              # Configuration Docker Compose
├── ml-backend/
│   ├── Dockerfile          # Image Python avec dépendances ML
│   ├── requirements.txt    # Packages Python
│   ├── download_models.py  # Script de pré-téléchargement Whisper
│   ├── _wsgi.py           # Point d'entrée Flask
│   ├── model.py           # Modèle Label Studio ML
│   ├── audio_segmenter.py # Logique de segmentation (VERSION STREAMING)
│   └── utils.py           # Utilitaires (download, convert)
└── README.md              # Ce fichier
```

## 🔮 Roadmap

- [x] Détection de zones de parole
- [x] Transcription avec Whisper
- [x] Support des gros fichiers (streaming)
- [x] Détection automatique de langue
- [x] Intégration Label Studio + MinIO
- [x] Templates pour projets religieux
- [ ] Support GPU pour accélération
- [ ] Diarization (identification des locuteurs automatique)
- [ ] Détection d'émotions
- [ ] Batch processing asynchrone
- [ ] Interface de monitoring
- [ ] Export des transcriptions en SRT/VTT

## 📄 License

Open-source - Utilisation libre

## ❔ Support

**En cas de problème** :

1. Consultez les logs : `docker-compose logs -f ml-backend`
2. Vérifiez la santé : `curl http://localhost:9090/health`
3. Testez manuellement : `curl http://localhost:9090/setup`
4. Consultez cette section de troubleshooting

**Les logs du ML Backend sont très verbeux** et vous diront exactement où le problème se situe.
