FROM node:24.13.0-alpine

WORKDIR /app

# On copie d'abord les fichiers de dépendances pour profiter du cache Docker
COPY package.json package-lock.json ./

# On installe les dépendances
RUN npm install

# On ne copie pas le reste du code ici car on va utiliser un volume 
# pour le développement (pour le HMR).
# Mais pour une image autonome (prod), on ferait COPY . .

EXPOSE 5173

# On autorise l'accès réseau externe pour Vite
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
