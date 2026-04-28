import { useState, useEffect, type ChangeEvent } from 'react'
import axios from 'axios'
import './App.css'
import { LogLevel, HubConnectionBuilder } from '@microsoft/signalr';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const SIGNALR_URL = "https://ns-function-app.azurewebsites.net/api";

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [jobId, setJobId] = useState('');
  const [status, setStatus] = useState('');
  const [tags, setTags] = useState<string[]>([]);

  // Initialisation de SignalR
  useEffect(() => {
    const newConnection = new HubConnectionBuilder()
      .withUrl(SIGNALR_URL)
      .withAutomaticReconnect()
      .configureLogging(LogLevel.Information)
      .build();

    newConnection.start()
      .then(() => {
        console.log("Connecté à SignalR !");
        
        // Écouter l'événement "newMessage" envoyé par les Functions
        newConnection.on("newMessage", (data) => {
          console.log("Notification reçue:", data);
          setStatus(data.status);
          setMessage(data.message);
          
          if (data.tags) {
            setTags(data.tags);
          }
        });
      })
      .catch(err => console.error("Erreur de connexion SignalR: ", err));

    return () => {
      newConnection.stop();
    };
  }, []);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleCreateAndUpload = async () => {
    if (!file) {
      alert("Please select a file first");
      return;
    }

    setLoading(true);
    setMessage('Creating job...');
    
    try {
      // 1. Create Job
      const createResponse = await axios.post(`${API_BASE_URL}/jobs`, {
        fileName: file.name,
        contentType: file.type || 'application/octet-stream'
      });

      const { jobId, uploadUrl } = createResponse.data;
      setJobId(jobId);
      setMessage(`Job created: ${jobId}. Uploading file...`);

      // 2. Upload to Blob Storage via SAS URL
      await axios.put(uploadUrl, file, {
        headers: {
          'x-ms-blob-type': 'BlockBlob',
          'Content-Type': file.type || 'application/octet-stream'
        }
      });

      setMessage(`File uploaded successfully for Job ${jobId}!`);
    } catch (error: any) {
      console.error(error);
      setMessage(`Error: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

return (
    <div className="App">
      <h1>Job & File Upload</h1>
      <div className="card">
        <input type="file" onChange={handleFileChange} />
        <button onClick={handleCreateAndUpload} disabled={loading || !file}>
          Upload & Analyser
        </button>
      </div>

      <div className="status-container">
        {jobId && <p><strong>ID du document:</strong> {jobId}</p>}
        {status && <p><strong>Statut:</strong> <span className={`badge ${status}`}>{status}</span></p>}
        {message && <p className="message">{message}</p>}
        
        {tags.length > 0 && (
          <div className="tags">
            <strong>Tags générés :</strong>
            {tags.map(tag => <span key={tag} className="tag">{tag}</span>)}
          </div>
        )}
      </div>
    </div>
  )
}

export default App
