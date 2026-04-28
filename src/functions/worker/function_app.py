import azure.functions as func
import logging
import json
import os
from datetime import datetime, timezone
from azure.cosmos import CosmosClient

app = func.FunctionApp()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ─────────────────────────────────────────
# FUNCTION 1 — Blob Trigger → Service Bus
# ─────────────────────────────────────────
@app.blob_trigger(
    arg_name="myblob",
    path="doc-storage/input/{name}",
    connection="docstoragens_STORAGE"
)
@app.service_bus_queue_output(
    arg_name="msg",
    queue_name="document-processing",
    connection="SERVICE_BUS_CONNECTION_STR"
)
def BlobToServiceBus(myblob: func.InputStream, msg: func.Out[str]):
    logging.info(f"[Function1] Traitement du blob : {myblob.name}")
    
    # Extraction du nom seul (ex: 123_cv.pdf)
    blob_full_path = myblob.name
    file_part = blob_full_path.split("/")[-1]

    # Parsing documentId et fileName selon le format id_nom.ext
    parts = file_part.split("_", 1)
    document_id = parts[0] if len(parts) >= 2 else "unknown"
    file_name = parts[1] if len(parts) >= 2 else file_part

    # Préparation du message JSON attendu par le TP
    message = {
        "documentId": document_id,
        "fileName": file_name,
        "blobName": blob_full_path,
        "size": myblob.length,
        "uploadedAt": now_iso()
    }

    # Envoi automatique vers Service Bus
    msg.set(json.dumps(message))
    
    logging.info(f"[Function1] Message envoyé pour documentId={document_id}")

# # ─────────────────────────────────────────
# # FUNCTION 2 — Service Bus → Cosmos DB
# # ─────────────────────────────────────────
# Initialisation du client Cosmos DB (à l'extérieur de la fonction pour la performance)
endpoint = os.environ["COSMOS_ENDPOINT"]
key = os.environ["COSMOS_KEY"]
client = CosmosClient(endpoint, key)
database = client.get_database_client("db-doc")
container_cosmos = database.get_container_client("doc-storage")

@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="document-processing",
    connection="SERVICE_BUS_CONNECTION_STR"
)
def ServiceBusWorker(msg: func.ServiceBusMessage):
    # 1. Lire et décoder le message
    message_body = msg.get_body().decode('utf-8')
    data = json.loads(message_body)
    
    doc_id = data['documentId']
    file_name = data['fileName'].lower()
    file_size = data['size']
    
    logging.info(f"[Function2] Traitement du document : {doc_id}")

    try:
        # 2. Règle : Vérifier si le fichier est vide
        if file_size == 0:
            update_cosmos_status(doc_id, "ERROR", [])
            logging.warning(f"Document {doc_id} vide. Statut ERROR.")
            return

        # 3. Logique de Tagging (basée sur l'énoncé du TP)
        tags = set()
        
        # Extensions
        if file_name.endswith('.pdf'): tags.update(['pdf', 'document'])
        elif file_name.endswith('.docx'): tags.update(['word', 'document'])
        elif file_name.endswith('.png'): tags.update(['image'])
        
        # Mots-clés
        keywords_map = {
            "cv": ["cv", "rh"],
            "facture": ["facture", "comptabilite"],
            "contrat": ["contrat", "administratif"],
            "azure": ["azure", "cloud"],
            "docker": ["docker", "devops"]
        }
        
        for key, value in keywords_map.items():
            if key in file_name:
                tags.update(value)

        # 4. Mise à jour Cosmos DB
        update_cosmos_status(doc_id, "PROCESSED", list(tags))
        logging.info(f"Document {doc_id} traité avec succès.")

    except Exception as e:
        logging.error(f"Erreur lors du traitement : {e}")
        # En cas d'erreur (ex: document introuvable), on peut mettre le statut à ERROR
        update_cosmos_status(doc_id, "ERROR", [])

def update_cosmos_status(doc_id, status, tags):
    # On récupère l'item existant
    item = container_cosmos.read_item(item=doc_id, partition_key='JOB')
    item['status'] = status
    item['tags'] = tags
    item['processedAt'] = datetime.now(timezone.utc).isoformat() + "Z"
    container_cosmos.replace_item(item=doc_id, body=item)