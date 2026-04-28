# import azure.functions as func
# import logging
# import json
# from datetime import datetime

# app = func.FunctionApp()

# @app.blob_trigger(arg_name="myblob", path="doc-storage/input/{name}",
#                                connection="docstoragens_STORAGE")
# @app.service_bus_queue_output(arg_name="msg", queue_name="document-processing", connection="SERVICE_BUS_CONNECTION_STR")
# def WorkerFile(myblob: func.InputStream, msg: func.Out[str]):
#     logging.info(f"Version CI/CD => Python blob trigger function processed blob"
#                 f"Name: {myblob.name}"
#                 f"Blob Size: {myblob.length} bytes")
#     full_path = myblob.name
#     blob_name_only = full_path.split('/')[-1]

#     try:
#         document_id, file_name = blob_name_only.split('_', 1)

#         message_data = {
#             "documentId": document_id,
#             "fileName": file_name,
#             "blobName": full_path,
#             "size": myblob.length,
#             "uploadedAt": datetime.utcnow().isoformat() + "Z"
#         }

#         msg.set(json.dumps(message_data))

#         logging.info(f"Message envoyé pour le document {document_id}")

#     except ValueError:
#         logging.error(f"le format du fichier {blob_name_only} est invalide. Attendu id_nom.ext")


import azure.functions as func
import logging
import json
from datetime import datetime, timezone

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
    queue_name="SERVICE_BUS_QUEUE_NAME",
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
# def generate_tags(file_name: str, size: int) -> list:
#     name_lower = file_name.lower()
#     tags = []

#     # Extension
#     if name_lower.endswith(".pdf"):
#         tags += ["pdf", "document"]
#     elif name_lower.endswith(".docx"):
#         tags += ["word", "document"]
#     elif name_lower.endswith(".png"):
#         tags += ["image"]

#     # Mots-clés
#     keywords = {
#         "cv": ["cv", "rh"],
#         "facture": ["facture", "comptabilite"],
#         "contrat": ["contrat", "administratif"],
#         "azure": ["azure", "cloud"],
#         "docker": ["docker", "devops"],
#     }
#     for keyword, keyword_tags in keywords.items():
#         if keyword in name_lower:
#             tags += keyword_tags

#     return list(set(tags))


# @app.service_bus_queue_trigger(
#     arg_name="msg",
#     queue_name="%SERVICE_BUS_QUEUE_NAME%",
#     connection="SERVICE_BUS_CONNECTION_STRING"
# )
# def ServiceBusTagger(msg: func.ServiceBusMessage):
#     body = msg.get_body().decode("utf-8")
#     data = json.loads(body)

#     document_id = data["documentId"]
#     file_name = data["fileName"]
#     size = data.get("size", 0)

#     logging.info(f"[Function2] Message reçu pour documentId={document_id}")

#     cosmos_client = CosmosClient(
#         url=os.environ["COSMOS_ENDPOINT"],
#         credential=os.environ["COSMOS_KEY"]
#     )
#     db = cosmos_client.get_database_client(os.environ["COSMOS_DATABASE"])
#     container = db.get_container_client(os.environ["COSMOS_CONTAINER"])

#     # Fichier vide
#     if size == 0:
#         logging.warning(f"[Function2] Fichier vide → ERROR")
#         try:
#             job = container.read_item(item=document_id, partition_key="JOB")
#             job["status"] = "ERROR"
#             job["error"] = "Fichier vide"
#             job["updatedAt"] = now_iso()
#             container.replace_item(document_id, job)
#         except Exception:
#             pass
#         return

#     # Chercher le document dans Cosmos
#     try:
#         job = container.read_item(item=document_id, partition_key="JOB")
#     except exceptions.CosmosResourceNotFoundError:
#         logging.error(f"[Function2] Document {document_id} introuvable → ERROR")
#         return

#     # Générer les tags
#     tags = generate_tags(file_name, size)

#     # Mettre à jour Cosmos
#     job["status"] = "PROCESSED"
#     job["tags"] = tags
#     job["fileName"] = file_name
#     job["processedAt"] = now_iso()
#     job["updatedAt"] = now_iso()
#     job.pop("error", None)

#     container.replace_item(document_id, job)
#     logging.info(f"[Function2] Document {document_id} → PROCESSED, tags={tags}")