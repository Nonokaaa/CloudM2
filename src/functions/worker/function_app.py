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
# NÉGOCIATION SIGNALR
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
    path_parts = myblob.name.split("/")
    document_id = path_parts[-2] if len(path_parts) >= 4 else "unknown"
    file_name = path_parts[-1]

    message = {
        "documentId": document_id,
        "fileName": file_name,
        "blobName": myblob.name,
        "size": myblob.length,
        "uploadedAt": now_iso()
    }
    msg.set(json.dumps(message))
    
    signalRMessages.set(json.dumps({
        "target": "newMessage",
        "arguments": [{
            "documentId": document_id,
            "status": "UPLOADED",
            "message": "Fichier reçu"
        }]
    }))
    update_cosmos_status(document_id, "QUEUED", [])

# ─────────────────────────────────────────
# FUNCTION 2 — Service Bus → Cosmos DB (CORRIGÉE)
# ─────────────────────────────────────────
endpoint = os.environ["COSMOS_ENDPOINT"]
key = os.environ["COSMOS_KEY"]
client = CosmosClient(endpoint, key)
database = client.get_database_client("db-doc")
container_cosmos = database.get_container_client("jobs")

def get_ai_client():
    ai_key = os.environ["AI_SERVICE_KEY"]
    ai_endpoint = os.environ["AI_SERVICE_ENDPOINT"]
    return TextAnalyticsClient(ai_endpoint, AzureKeyCredential(ai_key))

@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="document-processing",
    connection="SERVICE_BUS_CONNECTION_STR"
)
# CRUCIAL : Ajout du binding SignalR ici pour pouvoir envoyer des notifications
@app.generic_output_binding(
    arg_name="signalRMessages",
    type="signalR",
    hubName="documentsHub",
    connectionStringSetting="SIGNALR_CONNECTION_STRING"
)
def ServiceBusWorker(msg: func.ServiceBusMessage, signalRMessages: func.Out[str]):
    data = json.loads(msg.get_body().decode('utf-8'))
    doc_id = data['documentId']
    file_name = data['fileName']
    
    # 1. Notification : PROCESSING (Exigence 2 & 4 du sujet)
    signalRMessages.set(json.dumps({
        "target": "newMessage",
        "arguments": [{
            "documentId": doc_id,
            "status": "PROCESSING",
            "message": "Analyse IA en cours..."
        }]
    }))
    update_cosmos_status(doc_id, "PROCESSING", [])

    try:
        # 2. Analyse via Azure AI Language (Mots-clés)
        client_ai = get_ai_client()
        clean_name = file_name.replace("_", " ").replace("-", " ").split(".")[0]
        
        # Le "prompt" est implicite ici : on demande d'extraire les phrases clés
        response = client_ai.extract_key_phrases(documents=[clean_name])[0]
        tags = response.key_phrases if not response.is_error else []

        if not tags:
            tags = ["document", "archive"]

        # 3. Mise à jour Cosmos DB : PROCESSED
        update_cosmos_status(doc_id, "PROCESSED", tags)

        # 4. Notification finale : PROCESSED avec les tags
        signalRMessages.set(json.dumps({
            "target": "newMessage",
            "arguments": [{
                "documentId": doc_id,
                "status": "PROCESSED",
                "message": "Tagging terminé",
                "tags": tags
            }]
        }))

    except Exception as e:
        logging.error(f"Erreur Worker : {e}")
        update_cosmos_status(doc_id, "ERROR", [])
        signalRMessages.set(json.dumps({
            "target": "newMessage",
            "arguments": [{"documentId": doc_id, "status": "ERROR", "message": str(e)}]
        }))

def update_cosmos_status(doc_id, status, tags):
    item = container_cosmos.read_item(item=doc_id, partition_key='JOB')
    item['status'] = status
    item['tags'] = tags
    item['processedAt'] = now_iso()
    container_cosmos.replace_item(item=doc_id, body=item)