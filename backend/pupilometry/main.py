from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
import os
import uuid
import shutil
from pathlib import Path
from dotenv import load_dotenv
from src.ocr_utils import extract_tables_from_pdf
from src.doc_utils import process_json_to_docx
from src.uploadtoS3 import upload_file_to_s3 as upload_to_do_spaces, test_s3_connection as test_do_connection
import logging
import argparse
import traceback

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pupilometry PDF Processor", version="1.0.0")

# Add CORS middleware (aligned with pupilometry-lite FastAPI configuration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add exception handlers to ensure JSON responses
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all exceptions and return JSON responses"""
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors and return JSON responses"""
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)}
    )

# Create necessary directories
os.makedirs("uploads", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
os.makedirs("temp", exist_ok=True)

# Digital Ocean Spaces configuration
DO_BUCKET = os.getenv("DO_BUCKET_NAME")

def cleanup_files(*file_paths):
    """Clean up temporary files"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Warning: Could not delete {file_path}: {e}")

@app.get("/", response_class=HTMLResponse)
async def home():
    """Main page with file upload form"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pupilometry PDF Processor</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #2c3e50;
                text-align: center;
                margin-bottom: 30px;
            }
            .upload-form {
                text-align: center;
            }
            .file-input {
                margin: 20px 0;
                padding: 20px;
                border: 2px dashed #3498db;
                border-radius: 10px;
                background-color: #ecf0f1;
            }
            .file-input:hover {
                border-color: #2980b9;
                background-color: #d5dbdb;
            }
            input[type="file"] {
                width: 100%;
                padding: 10px;
                border: none;
                background: transparent;
            }
            .submit-btn {
                background-color: #3498db;
                color: white;
                padding: 15px 30px;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                cursor: pointer;
                transition: background-color 0.3s;
            }
            .submit-btn:hover {
                background-color: #2980b9;
            }
            .submit-btn:disabled {
                background-color: #bdc3c7;
                cursor: not-allowed;
            }
            .status {
                margin-top: 20px;
                padding: 15px;
                border-radius: 5px;
                display: none;
            }
            .status.success {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .status.error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .loading {
                display: none;
                text-align: center;
                margin: 20px 0;
            }
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #3498db;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔬 Pupilometry PDF Processor</h1>
            
            <div class="upload-form">
                <form id="uploadForm" enctype="multipart/form-data">
                    <div class="file-input">
                        <input type="file" id="pdfFile" name="file" accept=".pdf" required>
                        <p>📁 Click to select a PDF file or drag and drop</p>
                    </div>
                    
                    <button type="submit" class="submit-btn" id="submitBtn">
                        🚀 Process PDF
                    </button>
                </form>
                
                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p>Processing your PDF... Please wait.</p>
                </div>
                
                <div class="status" id="status"></div>
            </div>
        </div>

        <script>
            const form = document.getElementById('uploadForm');
            const fileInput = document.getElementById('pdfFile');
            const submitBtn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            const status = document.getElementById('status');

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const file = fileInput.files[0];
                if (!file) {
                    showStatus('Please select a PDF file', 'error');
                    return;
                }

                if (!file.name.toLowerCase().endsWith('.pdf')) {
                    showStatus('Please select a valid PDF file', 'error');
                    return;
                }

                // Show loading state
                submitBtn.disabled = true;
                loading.style.display = 'block';
                status.style.display = 'none';

                const formData = new FormData();
                formData.append('file', file);

                try {
                    const response = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });

                    // Check if response is JSON
                    const contentType = response.headers.get('content-type');
                    if (!contentType || !contentType.includes('application/json')) {
                        const text = await response.text();
                        showStatus(`❌ Error: Server returned non-JSON response. Status: ${response.status}`, 'error');
                        return;
                    }

                    const result = await response.json();

                    if (response.ok) {
                        showStatus(`✅ Success! Your document is ready: <a href="${result.url}" download>Download Document</a>`, 'success');
                    } else {
                        showStatus(`❌ Error: ${result.detail || 'Unknown error'}`, 'error');
                    }
                } catch (error) {
                    console.error('Upload error:', error);
                    showStatus(`❌ Error: ${error.message || 'Failed to process request'}`, 'error');
                } finally {
                    submitBtn.disabled = false;
                    loading.style.display = 'none';
                }
            });

            function showStatus(message, type) {
                status.innerHTML = message;
                status.className = `status ${type}`;
                status.style.display = 'block';
            }

            // Drag and drop functionality
            const fileInputDiv = document.querySelector('.file-input');
            
            fileInputDiv.addEventListener('dragover', (e) => {
                e.preventDefault();
                fileInputDiv.style.borderColor = '#2980b9';
                fileInputDiv.style.backgroundColor = '#d5dbdb';
            });

            fileInputDiv.addEventListener('dragleave', (e) => {
                e.preventDefault();
                fileInputDiv.style.borderColor = '#3498db';
                fileInputDiv.style.backgroundColor = '#ecf0f1';
            });

            fileInputDiv.addEventListener('drop', (e) => {
                e.preventDefault();
                fileInputDiv.style.borderColor = '#3498db';
                fileInputDiv.style.backgroundColor = '#ecf0f1';
                
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    fileInput.files = files;
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Process uploaded PDF and return local download link"""
    
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Generate unique filenames
    file_id = str(uuid.uuid4())
    pdf_path = f"uploads/{file_id}.pdf"
    json_path = f"temp/{file_id}.json"
    docx_path = f"outputs/{file_id}.docx"
    
    try:
        # Save uploaded PDF
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Process PDF to JSON
        extract_tables_from_pdf(pdf_path, json_path)
        
        # Convert JSON to DOCX
        process_json_to_docx(json_path, docx_path)
        
        logger.info(f"✅ PDF processed successfully, prepared for upload: {docx_path}")
        
        # Try Digital Ocean Spaces upload first
        do_key = f"pupilometry_documents/{file_id}.docx"
        if DO_BUCKET:
            url = upload_to_do_spaces(docx_path, DO_BUCKET, do_key, extra_args={'ACL': 'public-read'})
            if url:
                logger.info(f"✅ Uploaded to Digital Ocean Spaces: {url}")
                # Clean up all local artifacts after successful upload
                cleanup_files(pdf_path, json_path, docx_path)
                return {
                    "message": "PDF processed successfully and uploaded to Digital Ocean Spaces",
                    "url": url,
                    "file_id": file_id,
                    "upload_type": "digitalocean"
                }
        
        # Fallback: keep local file for download
        logger.warning("⚠️ Digital Ocean Spaces upload failed, falling back to local download")
        cleanup_files(pdf_path, json_path)
        download_url = f"/download/{file_id}"
        return {
            "message": "PDF processed successfully (Digital Ocean Spaces upload failed, local file available)",
            "url": download_url,
            "file_id": file_id,
            "upload_type": "local"
        }
        
    except Exception as e:
        # Clean up files on error
        cleanup_files(pdf_path, json_path, docx_path)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "Pupilometry PDF Processor"}

@app.get("/download/{file_id}")
async def download_file(file_id: str):
    """Download a processed Word document"""
    file_path = f"outputs/{file_id}.docx"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        filename=f"pupilometry_{file_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

# S3 test endpoints commented out - no longer using S3
# @app.get("/test-aws")
# async def test_aws_credentials():
#     """Test AWS credentials without uploading"""
#     try:
#         if not all([AWS_ACCESS_KEY, AWS_SECRET_KEY, S3_BUCKET]):
#             return {
#                 "status": "error",
#                 "message": "AWS credentials not fully configured",
#                 "details": {
#                     "region": AWS_REGION,
#                     "access_key": "✅" if AWS_ACCESS_KEY else "❌",
#                     "secret_key": "✅" if AWS_SECRET_KEY else "❌",
#                     "bucket": "✅" if S3_BUCKET else "❌"
#                 }
#             }
#         
#         # Test S3 connection
#         s3_ok = test_s3_connection()
#         return {
#             "s3_connection": "ok" if s3_ok else "failed",
#             "bucket_configured": bool(S3_BUCKET),
#             "region_configured": bool(AWS_REGION),
#             "credentials_configured": bool(AWS_ACCESS_KEY and AWS_SECRET_KEY),
#             "details": {
#                 "region": AWS_REGION,
#                 "bucket": S3_BUCKET,
#                 "access_key": f"{AWS_ACCESS_KEY[:8]}..." if AWS_ACCESS_KEY else "❌",
#                 "secret_key": f"{AWS_SECRET_KEY[:8]}..." if AWS_SECRET_KEY else "❌"
#             }
#         }
#             
#     except Exception as e:
#         return {
#             "status": "error",
#             "message": f"AWS credentials test failed: {str(e)}",
#             "details": {
#                 "region": AWS_REGION,
#                 "access_key": "✅" if AWS_ACCESS_KEY else "❌",
#                 "secret_key": "✅" if AWS_SECRET_KEY else "❌",
#                 "bucket": "✅" if S3_BUCKET else "❌"
#             }
#         }

# @app.get("/api/s3-test")
# async def test_s3_endpoint():
#     """Test S3 connection endpoint (alternative endpoint)"""
#     try:
#         s3_ok = test_s3_connection()
#         return {
#             "s3_connection": "ok" if s3_ok else "failed",
#             "bucket_configured": bool(S3_BUCKET),
#             "region_configured": bool(AWS_REGION),
#             "credentials_configured": bool(AWS_ACCESS_KEY and AWS_SECRET_KEY)
#         }
#     except Exception as e:
#         return {
#             "s3_connection": "error",
#             "error": str(e)
#         }

if __name__ == "__main__":
    import uvicorn
    
    # Optional visibility on Digital Ocean Spaces configuration
    if DO_BUCKET:
        logger.info("✅ Digital Ocean Spaces configured: uploads will attempt DO Spaces first")
        logger.info(f"   Bucket: {DO_BUCKET}")
    else:
        logger.warning("⚠️ Digital Ocean Spaces not fully configured. Falling back to local download when upload fails.")
    
    # Parse CLI args and environment for host/port
    parser = argparse.ArgumentParser(description="Run Pupilometry PDF Processor")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Host to bind")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port to bind")
    args = parser.parse_args()

    host = args.host
    port = args.port

    logger.info("🚀 Starting Pupilometry PDF Processor...")
    logger.info("📁 Created directories: uploads/, outputs/, temp/")
    logger.info(f"🌐 Server will be available at: http://{host}:{port}")
    
    # Test Digital Ocean Spaces connection if configured
    if DO_BUCKET:
        logger.info("🔍 Testing Digital Ocean Spaces connection...")
        if test_do_connection():
            logger.info("✅ Digital Ocean Spaces connection successful")
        else:
            logger.warning("⚠️ Digital Ocean Spaces connection test failed")
    
    uvicorn.run(app, host=host, port=port)
