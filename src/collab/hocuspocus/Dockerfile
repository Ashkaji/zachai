# Story 5.1 — Hocuspocus (Node 22 LTS). Build context: src/collab/hocuspocus
FROM node:22-alpine
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

ENV NODE_ENV=production
EXPOSE 1234
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
  CMD node -e "require('net').createConnection({port:1234,host:'127.0.0.1'},()=>process.exit(0)).on('error',()=>process.exit(1))"
CMD ["node", "dist/index.js"]
