import azure.functions as func
import logging
import json
from datetime import datetime

app = func.FunctionApp()

@app.blob_trigger(arg_name="myblob", path="doc-storage/input/{name}",
                               connection="docstoragens_STORAGE")
@app.service_bus_queue_output(arg_name="msg", queue_name="doc-sb-ns", connection="SERVICE_BUS_CONNECTION_STR")
def WorkerFile(myblob: func.InputStream, msg: func.Out[str]):
    logging.info(f"Version CI/CD => Python blob trigger function processed blob"
                f"Name: {myblob.name}"
                f"Blob Size: {myblob.length} bytes")
    full_path = myblob.name
    blob_name_only = full_path.split('/')[-1]

    try:
        document_id, file_name = blob_name_only.split('_', 1)

        message_data = {
            "documentId": document_id,
            "fileName": file_name,
            "blobName": full_path,
            "size": myblob.length,
            "uploadedAt": datetime.utcnow().isoformat() + "Z"
        }

        msg.set(json.dumps(message_data))

        logging.info(f"Message envoyé pour le document {document_id}")
        
    except ValueError:
        logging.error(f"le format du fichier {blob_name_only} est invalide. Attendu id_nom.ext")