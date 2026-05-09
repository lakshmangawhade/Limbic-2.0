"""
FastAPI Application for Cognitive & Limbic Report Processing
Production-ready API with security best practices.
"""
import os
import sys
import tempfile
import logging
import uuid
import time
from io import BytesIO
from typing import Optional, Dict
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, status, Query, Path, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from enum import Enum

from .pdf_processor import combine_reports, combine_reports_html, generate_unique_filename
from .storage_service import upload_to_spaces, check_s3_configuration
from .validators import validate_pdf_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class OutputFormat(str, Enum):
    """Output format options for processed documents."""
    HTML = "html"
    DOCX = "docx"


# In-memory storage for HTML files (with expiration)
# In production, consider using Redis or a database
html_file_storage: Dict[str, Dict] = {}
HTML_FILE_EXPIRY_SECONDS = 3600  # 1 hour

# Initialize FastAPI app
app = FastAPI(
    title="Cognitive & Limbic Report Processor API",
    description="API for processing PDF reports and generating combined HTML (default) or Word documents",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Security: Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Log startup information."""
    logger.info("=" * 60)
    logger.info("Starting FastAPI application...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Check S3 configuration
    config_ok, missing_vars = check_s3_configuration()
    if config_ok:
        logger.info("✅ DigitalOcean Spaces configured")
    else:
        logger.warning(f"⚠️ Missing S3 configuration: {', '.join(missing_vars)}")
        logger.info("💡 S3 upload will be disabled, but file processing will still work")
    
    logger.info("=" * 60)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Cognitive & Limbic Report Processor API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "process": "/process (HTML output - default)",
            "process_v2": "/process/v2 (DOCX output)",
            "process_with_metadata": "/process-pdf-with-metadata (JSON with metadata)",
            "view_html": "/view/{file_id} (View HTML output in browser)"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    config_ok, missing_vars = check_s3_configuration()
    return {
        "status": "healthy",
        "s3_configured": config_ok,
        "missing_s3_vars": missing_vars if not config_ok else []
    }


def cleanup_expired_html_files():
    """Remove expired HTML files from storage."""
    current_time = time.time()
    expired_keys = [
        key for key, value in html_file_storage.items()
        if current_time - value['created_at'] > HTML_FILE_EXPIRY_SECONDS
    ]
    for key in expired_keys:
        try:
            if os.path.exists(html_file_storage[key]['file_path']):
                os.unlink(html_file_storage[key]['file_path'])
            del html_file_storage[key]
            logger.info(f"Cleaned up expired HTML file: {key}")
        except Exception as e:
            logger.warning(f"Failed to cleanup HTML file {key}: {e}")


@app.get("/view/{file_id}", response_class=HTMLResponse)
async def view_html(file_id: str = Path(..., description="Unique file ID to view HTML")):
    """
    View HTML output in browser.
    
    Returns the HTML document for viewing. Files are stored temporarily and expire after 1 hour.
    """
    # Cleanup expired files
    cleanup_expired_html_files()
    
    # Check if file exists
    if file_id not in html_file_storage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HTML file not found or has expired. Please process the PDF again."
        )
    
    file_info = html_file_storage[file_id]
    
    # Check if file has expired
    if time.time() - file_info['created_at'] > HTML_FILE_EXPIRY_SECONDS:
        try:
            if os.path.exists(file_info['file_path']):
                os.unlink(file_info['file_path'])
            del html_file_storage[file_id]
        except Exception as e:
            logger.warning(f"Failed to cleanup expired file: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HTML file has expired. Please process the PDF again."
        )
    
    # Read and return HTML file
    try:
        with open(file_info['file_path'], 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Error reading HTML file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading HTML file: {str(e)}"
        )


@app.get("/_stcore/{path:path}")
@app.post("/_stcore/{path:path}")
async def handle_streamlit_requests(path: str):
    """
    Handle legacy Streamlit endpoint requests.
    Returns helpful message instead of generic 404.
    """
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "Streamlit endpoints are not available",
            "message": "This is a FastAPI application. Use /docs for API documentation.",
            "available_endpoints": {
                "root": "/",
                "health": "/health",
                "docs": "/docs",
                "redoc": "/redoc",
                "process_pdf": "/process-pdf"
            }
        }
    )


@app.post("/process")
async def process_pdf(
    file: UploadFile = File(..., description="PDF file to process"),
    format: OutputFormat = Query(
        default=OutputFormat.HTML,
        description="Output format: 'html' for HTML document (default) or 'docx' for Word document"
    )
):
    """
    Process PDF file and return combined document in specified format.
    
    **Output Formats:**
    - **html** (default): Returns HTML document following Dart Editor HTML guide format
    - **docx**: Returns Word document (DOCX format)
    
    **Security validations:**
    - File type validation (PDF only)
    - File size limits (50MB max)
    - PDF format verification (magic bytes)
    - Secure temporary file handling
    - HTML output sanitization (when format=html)
    """
    temp_file_path = None
    temp_output_path = None
    
    try:
        # Security: Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Security: Validate file
        is_valid, error_message = validate_pdf_file(file_content, file.filename, file_size)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Validation Error: {error_message}"
            )
        
        # Security: Create temporary file securely
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        # Initialize variables
        view_url = None
        file_id = None
        
        # Process based on format
        if format == OutputFormat.HTML:
            # Process the PDF to HTML
            logger.info(f"Processing PDF to HTML: {file.filename}")
            html_bytes = combine_reports_html(temp_file_path)
            
            # Create temporary file for HTML
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html', encoding='utf-8') as temp_html_file:
                temp_output_path = temp_html_file.name
                if isinstance(html_bytes, BytesIO):
                    html_bytes.seek(0)
                    html_content = html_bytes.read().decode('utf-8')
                    temp_html_file.write(html_content)
                else:  # It's a file path
                    with open(html_bytes, 'r', encoding='utf-8') as f_in:
                        temp_html_file.write(f_in.read())
            
            # Generate unique filename and file ID for viewing
            original_filename = os.path.basename(file.filename)
            unique_filename = generate_unique_filename(original_filename, extension=".html")
            file_id = str(uuid.uuid4())
            
            # Store HTML file for viewing (with expiration)
            html_file_storage[file_id] = {
                'file_path': temp_output_path,
                'filename': unique_filename,
                'created_at': time.time()
            }
            
            # Generate view URL
            base_url = os.getenv("BASE_URL", "http://localhost:8000")
            view_url = f"{base_url}/view/{file_id}"
            
            media_type = "text/html; charset=utf-8"
            
        else:  # DOCX format
            # Process the PDF to DOCX
            logger.info(f"Processing PDF to DOCX: {file.filename}")
            docx_bytes = combine_reports(temp_file_path)
            
            # Create temporary file for DOCX
            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_docx_file:
                temp_output_path = temp_docx_file.name
                if isinstance(docx_bytes, BytesIO):
                    docx_bytes.seek(0)
                    temp_docx_file.write(docx_bytes.read())
                else:  # It's a file path
                    with open(docx_bytes, 'rb') as f_in:
                        temp_docx_file.write(f_in.read())
            
            # Generate unique filename
            original_filename = os.path.basename(file.filename)
            unique_filename = generate_unique_filename(original_filename, extension=".docx")
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        
        # Try to upload to S3 (optional - don't fail if this doesn't work)
        s3_url = None
        s3_error = None
        try:
            s3_url, s3_filename = upload_to_spaces(temp_output_path)
            if not s3_url:
                config_ok, missing_vars = check_s3_configuration()
                if missing_vars:
                    s3_error = f"Missing DigitalOcean credentials: {', '.join(missing_vars)}"
                else:
                    s3_error = "Upload failed. Please check your DigitalOcean Spaces credentials and permissions."
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            s3_error = f"S3 upload error: {str(e)}"
        
        # Read output file for response
        with open(temp_output_path, 'rb') as f:
            output_content = f.read()
        
        # Prepare headers
        headers = {
            "Content-Disposition": f'attachment; filename="{unique_filename}"',
            "X-Filename": unique_filename,
            "X-S3-URL": s3_url or "",
            "X-S3-Error": s3_error or ""
        }
        
        # Add view URL for HTML format
        if format == OutputFormat.HTML:
            headers["X-View-URL"] = view_url
            headers["X-File-ID"] = file_id
        
        # Return file with metadata in headers
        return StreamingResponse(
            BytesIO(output_content),
            media_type=media_type,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing Error: {str(e)}"
        )
    finally:
        # Security: Cleanup temporary PDF file (keep HTML files for viewing)
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp PDF file: {e}")
        # Note: HTML files are kept in storage for viewing and cleaned up by expiration mechanism
        # DOCX files are cleaned up immediately after response
        if format == OutputFormat.DOCX and temp_output_path and os.path.exists(temp_output_path):
            try:
                os.unlink(temp_output_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp DOCX file: {e}")


@app.post("/process/v2")
async def process_pdf_docx(file: UploadFile = File(...)):
    """
    Process PDF file and return combined Word document (DOCX format - v2).
    
    Security validations:
    - File type validation (PDF only)
    - File size limits (50MB max)
    - PDF format verification (magic bytes)
    - Secure temporary file handling
    """
    temp_file_path = None
    temp_docx_path = None
    
    try:
        # Security: Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Security: Validate file
        is_valid, error_message = validate_pdf_file(file_content, file.filename, file_size)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Validation Error: {error_message}"
            )
        
        # Security: Create temporary file securely
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        # Process the PDF
        logger.info(f"Processing PDF to DOCX: {file.filename}")
        docx_bytes = combine_reports(temp_file_path)
        
        # Create temporary file for DOCX
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_docx_file:
            temp_docx_path = temp_docx_file.name
            if isinstance(docx_bytes, BytesIO):
                docx_bytes.seek(0)
                temp_docx_file.write(docx_bytes.read())
            else:  # It's a file path
                with open(docx_bytes, 'rb') as f_in:
                    temp_docx_file.write(f_in.read())
        
        # Generate unique filename
        original_filename = os.path.basename(file.filename)
        unique_filename = generate_unique_filename(original_filename, extension=".docx")
        
        # Try to upload to S3 (optional - don't fail if this doesn't work)
        s3_url = None
        s3_error = None
        try:
            s3_url, s3_filename = upload_to_spaces(temp_docx_path)
            if not s3_url:
                config_ok, missing_vars = check_s3_configuration()
                if missing_vars:
                    s3_error = f"Missing DigitalOcean credentials: {', '.join(missing_vars)}"
                else:
                    s3_error = "Upload failed. Please check your DigitalOcean Spaces credentials and permissions."
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            s3_error = f"S3 upload error: {str(e)}"
        
        # Read DOCX file for response
        with open(temp_docx_path, 'rb') as f:
            docx_content = f.read()
        
        # Return file with metadata in headers
        return StreamingResponse(
            BytesIO(docx_content),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{unique_filename}"',
                "X-Filename": unique_filename,
                "X-S3-URL": s3_url or "",
                "X-S3-Error": s3_error or ""
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing Error: {str(e)}"
        )
    finally:
        # Security: Cleanup temporary files
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp PDF file: {e}")
        if temp_docx_path and os.path.exists(temp_docx_path):
            try:
                os.unlink(temp_docx_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp DOCX file: {e}")


@app.post("/process-pdf-with-metadata")
async def process_pdf_with_metadata(
    request: Request,
    file: UploadFile = File(..., description="PDF file to process"),
    format: OutputFormat = Query(
        default=OutputFormat.HTML,
        description="Output format: 'html' for HTML document (default) or 'docx' for Word document"
    )
):
    """
    Process PDF file and return JSON response with metadata, file download URL, and view link.
    
    **Output Formats:**
    - **html** (default): Returns JSON with HTML view link and S3 URL
    - **docx**: Returns JSON with DOCX S3 URL
    
    **Response includes:**
    - `view_url`: Direct link to view HTML output in browser (HTML format only)
    - `s3_url`: S3/CDN URL for file download
    - `file_id`: Unique file ID for viewing (HTML format only)
    - `filename`: Generated unique filename
    - `file_size`: File size in bytes
    - `processed_at`: ISO timestamp of processing
    """
    temp_file_path = None
    temp_output_path = None
    view_url = None
    file_id = None
    
    try:
        # Security: Read and validate file
        file_content = await file.read()
        file_size = len(file_content)
        
        is_valid, error_message = validate_pdf_file(file_content, file.filename, file_size)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Validation Error: {error_message}"
            )
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        # Process based on format
        if format == OutputFormat.HTML:
            # Process PDF to HTML
            logger.info(f"Processing PDF to HTML: {file.filename}")
            try:
                html_bytes = combine_reports_html(temp_file_path)
            except Exception as e:
                logger.error(f"Error in combine_reports_html: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"HTML generation error: {str(e)}"
                )
            
            # Save HTML temporarily
            try:
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html', encoding='utf-8') as temp_html_file:
                    temp_output_path = temp_html_file.name
                    if isinstance(html_bytes, BytesIO):
                        html_bytes.seek(0)
                        html_content = html_bytes.read().decode('utf-8')
                        temp_html_file.write(html_content)
                    else:
                        with open(html_bytes, 'r', encoding='utf-8') as f_in:
                            temp_html_file.write(f_in.read())
            except Exception as e:
                logger.error(f"Error saving HTML file: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error saving HTML file: {str(e)}"
                )
            
            # Generate unique filename and file ID for viewing
            original_filename = os.path.basename(file.filename)
            unique_filename = generate_unique_filename(original_filename, extension=".html")
            file_id = str(uuid.uuid4())
            
            # Store HTML file for viewing (with expiration)
            html_file_storage[file_id] = {
                'file_path': temp_output_path,
                'filename': unique_filename,
                'created_at': time.time()
            }
            
            # Generate view URL - use request host to get the actual URL
            base_url = os.getenv("BASE_URL")
            if not base_url:
                # Get base URL from request
                scheme = request.url.scheme
                host = request.url.hostname
                port = request.url.port
                # Replace 0.0.0.0 with localhost for browser access
                if host == "0.0.0.0" or host == "127.0.0.1":
                    host = "localhost"
                if port:
                    base_url = f"{scheme}://{host}:{port}"
                else:
                    base_url = f"{scheme}://{host}"
            else:
                # Replace 0.0.0.0 with localhost if present in BASE_URL
                if "0.0.0.0" in base_url:
                    base_url = base_url.replace("0.0.0.0", "localhost")
            view_url = f"{base_url}/view/{file_id}"
            logger.info(f"Generated view URL for HTML: {view_url} (base_url: {base_url}, file_id: {file_id})")
            
        else:  # DOCX format
            # Process PDF to DOCX
            logger.info(f"Processing PDF to DOCX: {file.filename}")
            docx_bytes = combine_reports(temp_file_path)
            
            # Save DOCX temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_docx_file:
                temp_output_path = temp_docx_file.name
                if isinstance(docx_bytes, BytesIO):
                    docx_bytes.seek(0)
                    temp_docx_file.write(docx_bytes.read())
                else:
                    with open(docx_bytes, 'rb') as f_in:
                        temp_docx_file.write(f_in.read())
            
            # Generate filename
            original_filename = os.path.basename(file.filename)
            unique_filename = generate_unique_filename(original_filename, extension=".docx")
        
        # Upload to S3
        s3_url = None
        s3_error = None
        try:
            s3_url, s3_filename = upload_to_spaces(temp_output_path)
            if not s3_url:
                config_ok, missing_vars = check_s3_configuration()
                if missing_vars:
                    s3_error = f"Missing DigitalOcean credentials: {', '.join(missing_vars)}"
                else:
                    s3_error = "Upload failed. Please check credentials."
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            s3_error = f"S3 upload error: {str(e)}"
        
        # Get file size
        output_size = os.path.getsize(temp_output_path) if os.path.exists(temp_output_path) else 0
        
        # Build response
        response_data = {
            "success": True,
            "format": format.value,
            "filename": unique_filename,
            "s3_url": s3_url,
            "s3_error": s3_error,
            "file_size": output_size,
            "processed_at": datetime.now().isoformat()
        }
        
        # Add view URL and file ID for HTML format
        if format == OutputFormat.HTML:
            if view_url is None or file_id is None:
                logger.error(f"view_url or file_id is None for HTML format! view_url={view_url}, file_id={file_id}")
                # Generate a fallback view URL if somehow it wasn't set
                if file_id:
                    base_url = os.getenv("BASE_URL")
                    if not base_url:
                        # Get from request
                        scheme = request.url.scheme
                        host = request.url.hostname
                        port = request.url.port
                        if host == "0.0.0.0" or host == "127.0.0.1":
                            host = "localhost"
                        if port:
                            base_url = f"{scheme}://{host}:{port}"
                        else:
                            base_url = f"{scheme}://{host}"
                    else:
                        if "0.0.0.0" in base_url:
                            base_url = base_url.replace("0.0.0.0", "localhost")
                    view_url = f"{base_url}/view/{file_id}"
                    logger.info(f"Generated fallback view URL: {view_url}")
                else:
                    logger.error("Cannot generate view_url: file_id is None")
            response_data["view_url"] = view_url
            response_data["file_id"] = file_id
            logger.info(f"Returning HTML response - view_url: {view_url}, s3_url: {s3_url}, file_id: {file_id}")
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing Error: {str(e)}"
        )
    finally:
        # Cleanup temporary PDF file (keep HTML files for viewing)
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass
        # Note: HTML files are kept in storage for viewing and cleaned up by expiration mechanism
        # DOCX files are cleaned up immediately after response
        if format == OutputFormat.DOCX and temp_output_path and os.path.exists(temp_output_path):
            try:
                os.unlink(temp_output_path)
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
