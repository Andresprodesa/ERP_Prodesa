# =====================================================================================
# ERP Prodesa - imagen del frontend (SPA React/Vite servida por nginx, usuario no root).
# Build:  docker build -t erp-prodesa-frontend ./frontend
# /api se enruta al backend via nginx (ver nginx.conf, variable BACKEND_URL).
# =====================================================================================
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
# Copia explícita (no "COPY . .") para no arrastrar node_modules/dist del host Windows
COPY index.html vite.config.ts tsconfig*.json ./
COPY src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
ENV BACKEND_URL=http://backend:8000
# nginx:alpine procesa /etc/nginx/templates/*.template con envsubst al arrancar
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
