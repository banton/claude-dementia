import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from storage_service import S3StorageService

class TestS3StorageService(unittest.TestCase):
    @patch('storage_service.boto3.client')
    @patch.dict(os.environ, {
        'S3_ENDPOINT_URL': 'https://nyc3.digitaloceanspaces.com',
        'S3_ACCESS_KEY_ID': 'test-key',
        'S3_SECRET_ACCESS_KEY': 'test-secret',
        'S3_BUCKET_NAME': 'test-bucket',
        'S3_REGION_NAME': 'nyc3'
    })
    def test_upload_file(self, mock_boto_client):
        # Setup mock
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        service = S3StorageService()
        
        # Create a dummy file
        with open('test_upload.txt', 'w') as f:
            f.write('Hello S3')
            
        try:
            # Test upload
            result = service.upload_file('test_upload.txt')
            self.assertTrue(result)
            
            # Verify boto3 call
            mock_s3.upload_file.assert_called_once()
            args, kwargs = mock_s3.upload_file.call_args
            self.assertEqual(args[0], 'test_upload.txt')
            self.assertEqual(args[1], 'test-bucket')
            self.assertEqual(args[2], 'test_upload.txt')
            self.assertEqual(kwargs['ExtraArgs']['ContentType'], 'text/plain')
            self.assertEqual(kwargs['ExtraArgs']['ACL'], 'public-read')
            
        finally:
            if os.path.exists('test_upload.txt'):
                os.remove('test_upload.txt')

    @patch('storage_service.boto3.client')
    @patch.dict(os.environ, {
        'S3_ENDPOINT_URL': 'https://nyc3.digitaloceanspaces.com',
        'S3_ACCESS_KEY_ID': 'test-key',
        'S3_SECRET_ACCESS_KEY': 'test-secret',
        'S3_BUCKET_NAME': 'test-bucket',
        'S3_REGION_NAME': 'nyc3'
    })
    def test_list_files(self, mock_boto_client):
        # Setup mock
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        # Mock response
        mock_s3.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'file1.txt',
                    'Size': 123,
                    'LastModified': MagicMock(isoformat=lambda: '2023-01-01T00:00:00')
                }
            ]
        }
        
        service = S3StorageService()
        files = service.list_files()
        
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['key'], 'file1.txt')
        self.assertEqual(files[0]['size'], 123)

    @patch('storage_service.boto3.client')
    @patch.dict(os.environ, {
        'S3_ENDPOINT_URL': 'https://nyc3.digitaloceanspaces.com',
        'S3_ACCESS_KEY_ID': 'test-key',
        'S3_SECRET_ACCESS_KEY': 'test-secret',
        'S3_BUCKET_NAME': 'test-bucket',
        'S3_REGION_NAME': 'nyc3'
    })
    def test_get_file_url(self, mock_boto_client):
        # We need to mock boto3.client even if we don't use it in get_file_url 
        # because __init__ calls it.
        service = S3StorageService()
        url = service.get_file_url('test.txt')
        # Expected: https://test-bucket.nyc3.digitaloceanspaces.com/test.txt
        self.assertEqual(url, 'https://test-bucket.nyc3.digitaloceanspaces.com/test.txt')

if __name__ == '__main__':
    unittest.main()
