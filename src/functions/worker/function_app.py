import azure.functions as func
import logging
import json
import os
from datetime import datetime, timezone
from azure.cosmos import CosmosClient
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

app = func.FunctionApp()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ─────────────────────────────────────────
# NÉGOCIATION SIGNALR (Pour le Front-end)
# ─────────────────────────────────────────
@app.route(route="negotiate", auth_level=func.AuthLevel.ANONYMOUS)
@app.generic_input_binding(
    arg_name="connectionInfo", 
    type="signalRConnectionInfo", 
    hubName="documentsHub", 
    connectionStringSetting="SIGNALR_CONNECTION_STRING"
)
def negotiate(req: func.HttpRequest, connectionInfo) -> func.HttpResponse:
    return func.HttpResponse(connectionInfo)

# ─────────────────────────────────────────
# FUNCTION 1 — Blob Trigger → Service Bus
# ─────────────────────────────────────────
ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.docx'}
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
@app.generic_output_binding(
    arg_name="signalRMessages",
    type="signalR",
    hubName="documentsHub",
    connectionStringSetting="SIGNALR_CONNECTION_STRING"
)
def BlobToServiceBus(myblob: func.InputStream, msg: func.Out[str], signalRMessages: func.Out[str]):
    logging.info(f"[Function1] Traitement du blob : {myblob.name}")
    
    path_parts = myblob.name.split("/")
    file_name = path_parts[-1]

    parts = file_name.split("_", 1)
    document_id = parts[0] if len(parts) >= 2 else "unknown"
    extension = os.path.splitext(file_name)[1].lower()

    error_reason = None
    if myblob.length == 0 or myblob.length is None:
        error_reason = "Le fichier est vide (0 octet)."
    elif extension not in ALLOWED_EXTENSIONS:
        error_reason = f"Extension {extension} non supportée."
    
    if error_reason:
        logging.warning(f"Validation échouée pour {document_id} : {error_reason}")
        update_cosmos_status(document_id, "ERROR", [], error_msg=error_reason)
        signalRMessages.set(json.dumps({
            "target": "newMessage",
            "arguments": [{
                "documentId": document_id,
                "status": "ERROR",
                "message": error_reason
            }]
        }))
        return

    message = {
        "documentId": document_id,
        "fileName": file_name,
        "blobName": myblob.name,
        "size": myblob.length,
        "uploadedAt": now_iso()
    }

    # Envoi automatique vers Service Bus
    msg.set(json.dumps(message))
    
    # Notification UPLOADED demandée par le sujet
    signalRMessages.set(json.dumps({
        "target": "newMessage",
        "arguments": [{
            "documentId": document_id,
            "status": "UPLOADED",
            "message": "Fichier reçu"
        }]
    }))

    update_cosmos_status(document_id, "QUEUED", [])
    logging.info(f"[Function1] Terminé pour documentId={document_id}")

# # ─────────────────────────────────────────
# # FUNCTION 2 — Service Bus → Cosmos DB
# # ─────────────────────────────────────────
# Initialisation du client Cosmos DB (à l'extérieur de la fonction pour la performance)
endpoint = os.environ["COSMOS_ENDPOINT"]
key = os.environ["COSMOS_KEY"]
client = CosmosClient(endpoint, key)
database = client.get_database_client("db-doc")
container_cosmos = database.get_container_client("jobs")

# Initialisation du client AI
def get_ai_client():
    key = os.environ["AI_SERVICE_KEY"]
    endpoint = os.environ["AI_SERVICE_ENDPOINT"]
    return TextAnalyticsClient(endpoint, AzureKeyCredential(key))

@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="document-processing",
    connection="SERVICE_BUS_CONNECTION_STR"
)
@app.generic_output_binding(
    arg_name="signalRMessages",
    type="signalR",
    hubName="documentsHub",
    connectionStringSetting="SIGNALR_CONNECTION_STRING"
)
def ServiceBusWorker(msg: func.ServiceBusMessage, signalRMessages: func.Out[str]):
    message_body = msg.get_body().decode('utf-8')
    data = json.loads(message_body)
    doc_id = data['documentId']
    file_name = data['fileName'].lower()
    
    logging.info(f"[Function2] Traitement du document : {doc_id}")

    signalRMessages.set(json.dumps({
        "target": "newMessage",
        "arguments": [{
            "documentId": doc_id,
            "status": "PROCESSING",
            "message": "L'IA analyse votre document..."
        }]
    }))

    update_cosmos_status(doc_id, "PROCESSING", [])

    try:
        # 2. Appel à Azure AI pour extraire des mots-clés du nom de fichier
        client_ai = get_ai_client()
        # On nettoie un peu le nom (on enlève l'extension et les underscores)
        clean_name = file_name.replace("_", " ").replace("-", " ").split(".")[0]
        
        response = client_ai.extract_key_phrases(documents=[clean_name])[0]
        tags = response.key_phrases

        # Si l'IA ne trouve rien, on met un tag par défaut pour éviter un tableau vide
        if not tags:
            tags = ["document"]

        # 3. Mise à jour Cosmos DB
        update_cosmos_status(doc_id, "PROCESSED", tags)

        # 4. Notification finale PROCESSED
        signalRMessages.set(json.dumps({
            "target": "newMessage",
            "arguments": [{
                "documentId": doc_id,
                "status": "PROCESSED",
                "message": "Tags générés avec succès",
                "tags": tags
            }]
        }))

    except Exception as e:
        logging.error(f"Erreur : {e}")
        update_cosmos_status(doc_id, "ERROR", [])
        
        # NOTIFICATION "ERROR"
        signalRMessages.set(json.dumps({
            "target": "newMessage",
            "arguments": [{
                "documentId": doc_id,
                "status": "ERROR",
                "message": "Le traitement a échoué"
            }]
        }))

def update_cosmos_status(doc_id, status, tags, error_msg=None):
    try:
        item = container_cosmos.read_item(item=doc_id, partition_key='JOB')
        item['status'] = status
        item['tags'] = tags
        item['processedAt'] = datetime.now(timezone.utc).isoformat()
        if error_msg:
            item['errorMessage'] = error_msg
        container_cosmos.replace_item(item=doc_id, body=item)
    except Exception as e:
        logging.warning(f"Impossible de mettre à jour Cosmos : {e}")