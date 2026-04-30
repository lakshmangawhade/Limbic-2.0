import boto3, os, sys
from dotenv import load_dotenv
import logging
from typing import Union, Optional
from botocore.exceptions import ClientError # Import ClientError for better error handling

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()         # reads .env in project root

def upload_file_to_s3(local_path: str,
                      bucket: str,
                      key: Optional[str] = None,
                      extra_args: Optional[dict] = None) -> Optional[str]:
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

    # Check if file exists
    if not os.path.exists(local_path):
        logger.error(f"❌ File not found: {local_path}")
        return None

    # Retrieve DigitalOcean credentials/region from environment
    region     = os.getenv("DO_REGION")
    access_key = os.getenv("DO_ACCESS_KEY")
    secret_key = os.getenv("DO_ACCESS_SECRET")

    # All credentials are required for DigitalOcean
    if not all([region, access_key, secret_key]):
        logger.error("❌ DO_REGION, DO_ACCESS_KEY, or DO_ACCESS_SECRET not found in .env")
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

        s3.upload_file(local_path, bucket, key,
                        ExtraArgs=extra_args or {})

        # Construct the CDN URL, matching the JS example
        cdn_url = f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{key}"
        logger.info(f"✅ Uploaded  {local_path}  ➜  {cdn_url}")
        return cdn_url

    except ClientError as e:
        # More specific error logging
        if e.response['Error']['Code'] == 'InvalidAccessKeyId':
             logger.error(f"❌ Upload failed: Invalid credentials (DO_ACCESS_KEY).")
        elif e.response['Error']['Code'] == 'SignatureDoesNotMatch':
             logger.error(f"❌ Upload failed: Invalid credentials (DO_ACCESS_SECRET).")
        else:
             logger.error(f"❌ Upload failed (ClientError): {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error during upload: {e}")
        return None

def test_s3_connection() -> bool:
    """Test DigitalOcean Spaces connection and credentials"""
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
            aws_secret_access_key=secret_key,
        )
            
        # 1. Try to list buckets (tests credentials)
        s3.list_buckets()
        logger.info("✅ DigitalOcean Spaces connection test successful (Credentials OK)")
        
        # 2. Try to access the specific bucket (tests bucket name and permissions)
        s3.head_bucket(Bucket=bucket_name)
        logger.info(f"✅ Bucket '{bucket_name}' is accessible.")
        return True
        
    except ClientError as e:
        # Handle common errors gracefully
        if e.response['Error']['Code'] == 'NoSuchBucket':
             logger.error(f"❌ Connection successful, but bucket '{bucket_name}' not found.")
        elif e.response['Error']['Code'] == 'InvalidAccessKeyId':
             logger.error(f"❌ Connection failed: Invalid credentials (DO_ACCESS_KEY).")
        elif e.response['Error']['Code'] == 'SignatureDoesNotMatch':
             logger.error(f"❌ Connection failed: Invalid credentials (DO_ACCESS_SECRET).")
        elif e.response['Error']['Code'] == '403':
             logger.error(f"❌ Connection successful, but no permission to access bucket '{bucket_name}'.")
        else:
            logger.error(f"❌ DO Spaces connection test failed (ClientError): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ DO Spaces connection test failed (Exception): {e}")
        return False

# Test function for standalone testing
if __name__ == "__main__":
    print("Testing DigitalOcean Spaces connection...")
    if test_s3_connection():
        print("✅ DO Spaces connection is working")
        
        # --- Optional: Test the upload function ---
        print("\nTesting file upload...")
        
        # Create a dummy file to upload
        test_file_name = "do_test_upload.txt"
        try:
            with open(test_file_name, "w") as f:
                f.write("This is a test file for DigitalOcean Spaces upload.")
            
            bucket = os.getenv("DO_BUCKET_NAME")
            if bucket:
                # Use a specific key for the test
                test_key = f"test_uploads/{test_file_name}"
                
                # Make it public-read to be viewable via the CDN URL
                public_args = {'ACL': 'public-read'}
                
                print(f"Uploading '{test_file_name}' to 's3://{bucket}/{test_key}'...")
                upload_url = upload_file_to_s3(test_file_name,
                                               bucket,
                                               test_key,
                                               extra_args=public_args)
                
                if upload_url:
                    print(f"✅ Upload successful: {upload_url}")
                    print(f"ℹ  Note: You may need to clean up 's3://{bucket}/{test_key}' manually.")
                else:
                    print("❌ Upload test failed.")
            else:
                # This should have been caught by test_s3_connection, but good to double check
                print("❌ Cannot run upload test, DO_BUCKET_NAME not set.")
                
        finally:
            # Clean up local dummy file
            if os.path.exists(test_file_name):
                os.remove(test_file_name)
                
    else:
        print("❌ DO Spaces connection failed. Check .env variables and permissions.")



