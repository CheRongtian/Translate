# Local Translator

An offline document translation workflow based on local Large Language Models (LLMs). The frontend uses Streamlit for the user interface, while the backend utilizes Ollama for local model inference.

## Features

- **Fully Offline Processing**: All text parsing and machine translation operate locally without external network requests.
- **Multiple File Format Support**:
  - Plain Text (TXT)
  - Documents (PDF, DOCX)
  - Images (PNG, JPG, JPEG) - Integrated with Tesseract OCR engine.
- **Decoupled Architecture**: The frontend focuses on file parsing and API invocation. The backend inference model can be hot-swapped by modifying the `model` parameter in the codebase.

## Architecture Overview

The system consists of two layers:
1. **Interaction & Parsing Layer (Frontend)**: Handles file uploads and extracts text content using `PyPDF2`, `python-docx`, and `pytesseract`.
2. **Inference Layer (Backend)**: The Ollama service running on the host machine executes the open-source LLM, receives JSON requests from the frontend, and returns the translation results.

## Prerequisites (Host Machine)
Before running this project, the host machine must be configured with the Ollama service and the corresponding model:

1. **Install Ollama**: Visit [ollama.com](https://ollama.com/) to download and install the software.
2. **Download Inference Model**: Execute the following command in the terminal to pull the Qwen 7B model (default configuration):
```bash
   ollama run qwen:7b
```

*Note: Ensure the Ollama service is running in the background (default port 11434) after the download completes.*

## Deployment & Usage
Using Docker for environment isolation is highly recommended to avoid OCR engine configuration conflicts across different operating systems.

### Method 1: Docker Deployment (Recommended)

1. **Build the Image**:
Execute the following command in the project root directory:
```bash
docker build -t local-translator .
```

2. **Run the Container**:
Execute the following command. The service inside the container will access the host's Ollama API via `host.docker.internal`:
```bash
docker run -p 8501:8501 local-translator
```

3. **Access the Service**:
Open a web browser and navigate to `http://localhost:8501`.

### Method 2: Direct Source Code Execution

If not using Docker, complete dependencies must be configured on the host machine:

1. **Install OCR System Dependencies (macOS example)**:
```bash
brew install tesseract tesseract-lang
```

2. **Install Python Dependencies**:
```bash
pip install -r requirements.txt
```

3. **Modify Configuration**:
Open `app.py` and change the API request URL from `http://host.docker.internal:11434/api/generate` to the local address `http://localhost:11434/api/generate`.

4. **Start the Service**:
```bash
streamlit run app.py
```