import os
import boto3
from botocore.exceptions import ClientError
import mimetypes
import asyncio
from typing import Optional, Dict, Any, List

class S3StorageService:
    def __init__(self):
        self.endpoint_url = os.getenv('S3_ENDPOINT_URL')
        self.access_key = os.getenv('S3_ACCESS_KEY_ID')
        self.secret_key = os.getenv('S3_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        self.region_name = os.getenv('S3_REGION_NAME')

        if not all([self.endpoint_url, self.access_key, self.secret_key, self.bucket_name]):
            print("Warning: S3 environment variables are not fully set. Storage tools will fail if used.")
            self.client = None
        else:
            self.client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region_name
            )

    def upload_file(self, file_path, object_name=None):
        """Upload a file to an S3 bucket

        :param file_path: File to upload
        :param object_name: S3 object name. If not specified then file_name is used
        :return: True if file was uploaded, else False
        """
        if not self.client:
            raise ValueError("S3 client not initialized. Check environment variables.")

        # If S3 object_name was not specified, use file_name
        if object_name is None:
            object_name = os.path.basename(file_path)

        # Check file size (max 10MB)
        file_size = os.path.getsize(file_path)
        if file_size > 10 * 1024 * 1024:
            raise ValueError(f"File {file_path} exceeds maximum size of 10MB.")

        # Guess content type
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'

        try:
            extra_args = {'ContentType': content_type, 'ACL': 'public-read'}
            self.client.upload_file(
                file_path, 
                self.bucket_name, 
                object_name, 
                ExtraArgs=extra_args
            )
            print(f"Successfully uploaded {file_path} to {self.bucket_name}/{object_name}")
            return True
        except ClientError as e:
            print(f"Failed to upload {file_path}: {e}")
            raise e

    def list_files(self, prefix=None):
        """List files in the bucket"""
        if not self.client:
            raise ValueError("S3 client not initialized.")

        try:
            args = {'Bucket': self.bucket_name}
            if prefix:
                args['Prefix'] = prefix
            
            response = self.client.list_objects_v2(**args)
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'].isoformat()
                    })
            return files
        except ClientError as e:
            print(f"Failed to list files: {e}")
            raise e

    def get_file_url(self, object_name):
        """Get public URL for a file"""
        if not self.client:
            raise ValueError("S3 client not initialized.")
            
        # Assuming public-read ACL and standard DigitalOcean Spaces URL format
        # https://bucket-name.region.digitaloceanspaces.com/object-name
        # Or endpoint_url/bucket_name/object_name depending on config
        
        # A safer way might be to construct it from endpoint
        # DigitalOcean Spaces: https://{bucket}.{region}.digitaloceanspaces.com/{key}
        # But endpoint_url usually is https://{region}.digitaloceanspaces.com
        
        # Let's try to construct it simply first
        url = f"{self.endpoint_url}/{self.bucket_name}/{object_name}"
        
        # If endpoint_url doesn't include bucket, we might need to adjust. 
        # But for now, let's assume the user wants the direct link.
        # Actually, for DO Spaces, if endpoint is nyc3.digitaloceanspaces.com, 
        # public URL is https://bucket.nyc3.digitaloceanspaces.com/key
        
        if "digitaloceanspaces.com" in self.endpoint_url:
             # Parse region from endpoint if possible, or use provided region
             # endpoint: https://nyc3.digitaloceanspaces.com
             # bucket: mybucket
             # url: https://mybucket.nyc3.digitaloceanspaces.com/key

             clean_endpoint = self.endpoint_url.replace("https://", "").replace("http://", "")
             url = f"https://{self.bucket_name}.{clean_endpoint}/{object_name}"

        return url

    # ============================================================================
    # ASYNC WRAPPERS (using run_in_executor to prevent event loop blocking)
    # ============================================================================

    async def upload_file_async(self, file_path: str, object_name: Optional[str] = None) -> bool:
        """
        Async wrapper for upload_file.

        Prevents event loop blocking by running sync boto3 operations in executor.

        Args:
            file_path: File to upload
            object_name: S3 object name (defaults to filename)

        Returns:
            True if file was uploaded, else raises exception
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.upload_file,
            file_path,
            object_name
        )

    async def list_files_async(self, prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Async wrapper for list_files.

        Args:
            prefix: Optional prefix to filter files

        Returns:
            List of file dictionaries
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.list_files,
            prefix
        )

    async def get_file_url_async(self, object_name: str) -> str:
        """
        Async wrapper for get_file_url.

        Args:
            object_name: S3 object name

        Returns:
            Public URL for the file
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.get_file_url,
            object_name
        )
