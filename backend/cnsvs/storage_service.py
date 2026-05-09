"""
DigitalOcean Spaces Storage Service
Handles file uploads to DigitalOcean Spaces with proper error handling and security.
"""
import boto3
import os
import logging
import time
import random
from botocore.exceptions import ClientError
from typing import Optional, Tuple
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


def generate_unique_filename(fieldname: str) -> str:
    """
    Generates a unique filename based on the fieldname, current time,
    and a random number.
    
    Args:
        fieldname: The original filename or identifier
    
    Returns:
        A string for the new, unique filename
    """
    timestamp = int(time.time() * 1000)
    random_num = round(random.random() * 1e9)
    unique_suffix = f"{timestamp}-{random_num}"
    return f"{fieldname}-{unique_suffix}"


def upload_file_to_spaces(
    local_path: str,
    bucket: str,
    key: Optional[str] = None,
    extra_args: Optional[dict] = None
) -> Optional[str]:
    """
    Upload local_path to DigitalOcean Spaces.

    Parameters
    ----------
    local_path : str  –  path to the file on disk
    bucket     : str  –  target bucket name
    key        : str  –  destination path in the bucket (defaults to filename)
    extra_args : dict –  e.g. {'ACL': 'public-read'}

    Returns
    -------
    Optional[str]
        The public CDN URL of the uploaded file, or None on failure.
    """
    if key is None:
        key = os.path.basename(local_path)

    # Security: Check if file exists
    if not os.path.exists(local_path):
        logger.error(f"❌ File not found: {local_path}")
        return None

    # Retrieve DigitalOcean credentials/region from environment
    region = os.getenv("DO_REGION")
    access_key = os.getenv("DO_ACCESS_KEY")
    secret_key = os.getenv("DO_ACCESS_SECRET")

    # Security: All credentials are required
    if not all([region, access_key, secret_key]):
        logger.error("❌ DO_REGION, DO_ACCESS_KEY, or DO_ACCESS_SECRET not found in environment")
        return None
        
    endpoint_url = f"https://{region}.digitaloceanspaces.com"

    try:
        s3 = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        s3.upload_file(local_path, bucket, key, ExtraArgs=extra_args or {})

        # Construct the CDN URL
        cdn_url = f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{key}"
        logger.info(f"✅ Uploaded {local_path} ➜ {cdn_url}")
        return cdn_url

    except ClientError as e:
        # Security: Detailed error logging without exposing sensitive info
        if e.response['Error']['Code'] == 'InvalidAccessKeyId':
            logger.error("❌ Upload failed: Invalid credentials (DO_ACCESS_KEY)")
        elif e.response['Error']['Code'] == 'SignatureDoesNotMatch':
            logger.error("❌ Upload failed: Invalid credentials (DO_ACCESS_SECRET)")
        else:
            logger.error(f"❌ Upload failed (ClientError): {e.response['Error']['Code']}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error during upload: {e}")
        return None


def upload_to_spaces(local_path: str, prefix: str = "") -> Tuple[Optional[str], Optional[str]]:
    """
    Upload a file to DigitalOcean Spaces with a prefix.
    
    Parameters
    ----------
    local_path : str  –  path to the file on disk
    prefix     : str  –  prefix to add to the key (e.g., "medical-documents/")
    
    Returns
    -------
    Tuple[Optional[str], Optional[str]]
        A tuple of (CDN URL, filename) or (None, None) on failure.
    """
    bucket = os.getenv("DO_BUCKET_NAME")
    if not bucket:
        logger.error("❌ DO_BUCKET_NAME not found in environment")
        return None, None
    
    # Extract original filename and extension
    original_filename = os.path.basename(local_path)
    filename_without_ext, file_extension = os.path.splitext(original_filename)
    
    # Generate unique filename
    unique_filename_base = generate_unique_filename(filename_without_ext)
    unique_filename = f"{unique_filename_base}{file_extension}"
    
    # Construct the key with prefix
    key = f"{prefix}{unique_filename}" if prefix else unique_filename
    
    # Upload the file (make it public-read by default)
    cdn_url = upload_file_to_spaces(
        local_path=local_path,
        bucket=bucket,
        key=key,
        extra_args={'ACL': 'public-read'}
    )
    
    if cdn_url:
        return cdn_url, key
    return None, None


def test_spaces_connection() -> bool:
    """
    Test DigitalOcean Spaces connection and credentials.
    
    Returns
    -------
    bool
        True if connection successful, False otherwise
    """
    try:
        region = os.getenv("DO_REGION")
        access_key = os.getenv("DO_ACCESS_KEY")
        secret_key = os.getenv("DO_ACCESS_SECRET")
        bucket_name = os.getenv("DO_BUCKET_NAME")

        if not bucket_name:
            logger.error("❌ DO_BUCKET_NAME not set in environment")
            return False
            
        if not region:
            logger.error("❌ DO_REGION not set in environment")
            return False
            
        if not (access_key and secret_key):
            logger.error("❌ DO_ACCESS_KEY or DO_ACCESS_SECRET not set in environment")
            return False

        endpoint_url = f"https://{region}.digitaloceanspaces.com"

        s3 = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
            
        # Test credentials
        s3.list_buckets()
        logger.info("✅ DigitalOcean Spaces connection test successful (Credentials OK)")
        
        # Test bucket access
        s3.head_bucket(Bucket=bucket_name)
        logger.info(f"✅ Bucket '{bucket_name}' is accessible")
        return True
        
    except ClientError as e:
        # Security: Handle errors without exposing sensitive info
        if e.response['Error']['Code'] == 'NoSuchBucket':
            logger.error(f"❌ Connection successful, but bucket '{bucket_name}' not found")
        elif e.response['Error']['Code'] == 'InvalidAccessKeyId':
            logger.error("❌ Connection failed: Invalid credentials (DO_ACCESS_KEY)")
        elif e.response['Error']['Code'] == 'SignatureDoesNotMatch':
            logger.error("❌ Connection failed: Invalid credentials (DO_ACCESS_SECRET)")
        elif e.response['Error']['Code'] == '403':
            logger.error(f"❌ Connection successful, but no permission to access bucket '{bucket_name}'")
        else:
            logger.error(f"❌ DO Spaces connection test failed (ClientError): {e.response['Error']['Code']}")
        return False
    except Exception as e:
        logger.error(f"❌ DO Spaces connection test failed (Exception): {e}")
        return False


def check_s3_configuration() -> Tuple[bool, list]:
    """
    Check if DigitalOcean Spaces configuration is available.
    
    Returns
    -------
    Tuple[bool, list]
        (True if configured, list of missing variables)
    """
    bucket = os.getenv("DO_BUCKET_NAME")
    region = os.getenv("DO_REGION")
    access_key = os.getenv("DO_ACCESS_KEY")
    secret_key = os.getenv("DO_ACCESS_SECRET")
    
    missing = []
    if not bucket:
        missing.append("DO_BUCKET_NAME")
    if not region:
        missing.append("DO_REGION")
    if not access_key:
        missing.append("DO_ACCESS_KEY")
    if not secret_key:
        missing.append("DO_ACCESS_SECRET")
    
    return len(missing) == 0, missing

