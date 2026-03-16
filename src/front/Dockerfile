# Stage 1: Build the React application
FROM node:20-alpine AS build

# Ces arguments permettent d'injecter l'URL de l'API Azure pendant la construction
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

WORKDIR /app

# Installation des dépendances
COPY package*.json ./
RUN npm install

# Copie du code source et build
COPY . .
RUN npm run build

# Stage 2: Serve the application using Nginx
FROM nginx:stable-alpine

# On copie les fichiers compilés du stage 1 vers le dossier que Nginx sert par défaut
COPY --from=build /app/dist /usr/share/nginx/html

# Exposition du port web standard
EXPOSE 80

# Démarrage de nginx
CMD ["nginx", "-g", "daemon off;"]
