import { useState, type ChangeEvent } from 'react'
import axios from 'axios'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [jobId, setJobId] = useState('');

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
        <br /><br />
        <button onClick={handleCreateAndUpload} disabled={loading || !file}>
          {loading ? 'Processing...' : 'Create Job & Upload File'}
        </button>
      </div>
      {message && <p className="message">{message}</p>}
      {jobId && <p><strong>Job ID:</strong> {jobId}</p>}
    </div>
  )
}

export default App
