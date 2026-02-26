# Utilisation d'une image légère pour économiser de l'espace et du temps de build
FROM python:3.11-slim

# Définition du dossier de travail
WORKDIR /app

# Copie du fichier de dépendances
COPY requirements.txt .

# Installation des dépendances sans cache pour réduire la taille de l'image
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source (depuis le dossier src/api vers /app)
COPY . .

# Exposition du port utilisé par FastAPI
EXPOSE 8000

# Commande de lancement (adapter si le fichier principal est différent)
# On utilise uvicorn pour lancer l'app située dans app.main
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
