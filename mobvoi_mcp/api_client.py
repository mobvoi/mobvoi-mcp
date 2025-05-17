import concurrent.futures
import hashlib
import os
import time
from pathlib import Path

import httpx


def download_file_multi_thread(url: str, output_path: str, num_threads: int = 4, chunk_size: int = 1024*1024):
    """Download a file from a URL using multiple threads.
    
    Args:
        url: The URL of the file to download
        output_path: The path where the file should be saved
        num_threads: Number of threads to use for downloading
        chunk_size: Size of each chunk in bytes
    """
    # Create directory if it doesn't exist
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Get file size
    with httpx.Client() as client:
        response = client.head(url, follow_redirects=True)
        response.raise_for_status()
        file_size = int(response.headers.get('Content-Length', 0))
    
    if file_size == 0:
        # Can't use multi-threading if we don't know the file size
        with httpx.Client() as client:
            with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
        return
    
    # Calculate chunk ranges
    ranges = []
    for i in range(num_threads):
        start = i * (file_size // num_threads)
        end = (i + 1) * (file_size // num_threads) - 1 if i < num_threads - 1 else file_size - 1
        ranges.append((start, end))
    
    # Create temporary directory for chunks
    temp_dir = os.path.join(os.path.dirname(output_path), f".download_temp_{int(time.time())}")
    os.makedirs(temp_dir, exist_ok=True)
    
    def download_chunk(range_index):
        start, end = ranges[range_index]
        range_header = {'Range': f'bytes={start}-{end}'}
        temp_file = os.path.join(temp_dir, f"chunk_{range_index}")
        
        with httpx.Client() as client:
            with client.stream("GET", url, headers=range_header, follow_redirects=True) as response:
                response.raise_for_status()
                with open(temp_file, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
        return temp_file
    
    # Download chunks in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(download_chunk, i) for i in range(len(ranges))]
        chunk_files = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    # Combine chunks
    with open(output_path, 'wb') as output_file:
        for i in range(len(ranges)):
            chunk_file = os.path.join(temp_dir, f"chunk_{i}")
            with open(chunk_file, 'rb') as chunk:
                output_file.write(chunk.read())
    
    # Clean up temp files
    for file in os.listdir(temp_dir):
        os.remove(os.path.join(temp_dir, file))
    os.rmdir(temp_dir)

def download_file(url: str, output_path: str, timeout: int = 30):
    """
    Download a file from URL to the specified output path using streaming.
    
    Args:
        url: URL to download from
        output_path: Path where the file will be saved
        timeout: Timeout in seconds for the request
    """
    # Ensure directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
    except httpx.TimeoutException:
        raise Exception(f"Request timed out: {url}")
    except httpx.RequestError as e:
        raise Exception(f"Request error occurred: {str(e)}")
    except IOError as e:
        raise Exception(f"I/O error occurred when writing file: {str(e)}")

class ServiceNotFoundError(Exception):
    def __init__(self, service: str, region: str):
        super().__init__(f"Service '{service}' not found in region '{region}', check your region and service name")

class ApiClient:
    def __init__(self, app_key: str, app_secret: str, region: str = "mainland"):
        self.__app_key = app_key
        self.__app_secret = app_secret

        self.__region = region

        self.__client = httpx.Client(
            timeout=20
        )

        mainland_tts_host = "https://open.mobvoi.com"
        mainland_avatar_host = "https://openman.weta365.com/metaman/open"

        self.__service_dict = {
            "mainland": {
                # naming: {group_name}.{service_name}
                "tts.get_speaker_list": f"{mainland_tts_host}/api/tts/getSpeakerList",
                "tts.text_to_speech": f"{mainland_tts_host}/api/tts/v1",
                "tts.voice_clone": f"{mainland_tts_host}/clone",
                "avatar.photo_drive_avatar": f"{mainland_avatar_host}/image/toman/cmp",
                "avatar.query_photo_drive_avatar": f"{mainland_avatar_host}/image/toman/cmp/result/",
                "avatar.video_dubbing": f"{mainland_avatar_host}/video/voiceover/createTask",
                "avatar.query_video_dubbing": f"{mainland_avatar_host}/video/voiceover/detail",
            },
            "global": {

            }
        }

    def __get_url(self, service: str):
        regional_service_dict = self.__service_dict.get(self.__region, None)
        if regional_service_dict is None:
            raise ServiceNotFoundError(service, self.__region)
        service_url = regional_service_dict.get(service, None)
        if service_url is None:
            raise ServiceNotFoundError(service, self.__region)
        return service_url

    def __parse_signature(self):
        if self.__region == "mainland":
            timestamp = int(time.time())
            signature = hashlib.md5(f"{self.__app_key}+{self.__app_secret}+{timestamp}".encode()).hexdigest()
            signature_info = {
                "appKey": self.__app_key,
                "signature": signature,
                "timestamp": str(timestamp),
            }
        elif self.__region == "global":
            # TODO: implement global signature
            signature_info = {}
        return signature_info

    def post(self, service: str, request: dict = {}, headers: dict = {}, data: dict = {}, file: dict = {}, path: str = ""):
        post_header = self.__parse_signature()
        post_header.update(headers)

        url = self.__get_url(service)
        if path:
            url = f"{url}/{path}"

        response = self.__client.post(url, headers=post_header, json=request, data=data, files=file)
        return response

    def get(self, service: str, request: dict = {}, headers: dict = {}, path: str = ""):
        get_header = self.__parse_signature()
        get_header.update(headers)

        url = self.__get_url(service)
        if path:
            url = f"{url}/{path}"

        response = self.__client.get(url, headers=get_header, params=request)
        return response
