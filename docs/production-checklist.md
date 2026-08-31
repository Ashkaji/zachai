# 🏁 Checklist de Mise en Production (ZachAI)

Ce document décrit les étapes nécessaires pour déployer ZachAI sur un serveur Linux distant (VPS, Cloud, etc.).

## 1. Architecture Réseau & HTTPS
En production, vous ne devez pas exposer tous les ports (8000, 5173, 9001). Seul le port **443 (HTTPS)** doit être ouvert.
- **Reverse Proxy** : Utilisez **Nginx** ou **Traefik** sur l'hôte.
- **Certificats SSL** : Utilisez **Let's Encrypt** (Certbot) pour avoir du HTTPS gratuit.
- **Mapping des URLs** :
  - `https://zachai.com` → `frontend:80`
  - `https://zachai.com/v1` → `fastapi:8000`
  - `https://zachai.com/collab` → `hocuspocus:1234`
  - `https://zachai.com/auth` → `keycloak:8080`

## 2. Docker Frontend (Production)
Le `Dockerfile` actuel est pour le développement. Pour la prod, créez un `Dockerfile.prod` :
```dockerfile
# Etape 1 : Build
FROM node:24-alpine as build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Etape 2 : Service avec Nginx
FROM nginx:stable-alpine
COPY --from=build-stage /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## 3. Sécurité des Données
- **Variables d'environnement** : Créez un fichier `.env` sur le serveur.
- **Passwords** : Changez `POSTGRES_PASSWORD` et `MINIO_ROOT_PASSWORD` par des chaînes complexes.
- **Keycloak** : Changez le mode `start-dev` en `start` et configurez le `KC_HOSTNAME` avec votre vrai domaine.

## 4. Performance & IA
- **Diarization Worker** : En production, si vous avez un GPU (Nvidia), changez la variable `DIARIZATION_DEVICE` de `cpu` à `cuda` pour des performances 10x plus rapides.
- **Resources** : Augmentez la RAM allouée au `diarization-worker` et `openvino-worker` (8 Go recommandés pour l'IA).

## 5. Maintenance
- **Logs** : Configurez une rotation des logs Docker pour éviter de remplir le disque dur.
- **Backups** : Prévoyez un script `cron` qui fait un `pg_dump` de la base de données toutes les nuits.
