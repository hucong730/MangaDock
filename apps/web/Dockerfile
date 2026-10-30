FROM node:22-alpine

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json apps/web/
RUN npm ci --prefix apps/web --no-audit --no-fund

COPY apps/web/index.html apps/web/tsconfig.json apps/web/tsconfig.app.json apps/web/tsconfig.node.json apps/web/vite.config.ts apps/web/
COPY apps/web/src apps/web/src

EXPOSE 5173

CMD ["npm", "run", "dev", "--prefix", "apps/web", "--", "--port", "5173"]
