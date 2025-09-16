import os
import requests
import whisper
from typing import Optional, Dict, Any
import tempfile
from urllib.parse import urlparse
import aiohttp
import asyncio
from datetime import datetime
import traceback
from dotenv import load_dotenv
import subprocess
import shutil

load_dotenv()

CALLRAIL_API_BASE = "https://api.callrail.com/v3"
CALLRAIL_BEARER_TOKEN = os.getenv("CALLRAIL_BEARER_TOKEN")
if not CALLRAIL_BEARER_TOKEN:
    raise ValueError("CALLRAIL_BEARER_TOKEN not found in environment variables")

class CallProcessor:
    def __init__(self):
        self.bearer_token = CALLRAIL_BEARER_TOKEN
        # Initialize Whisper model
        self.model = whisper.load_model("base")
        # Check if FFmpeg is available
        self.ffmpeg_available = self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available in the system"""
        # First try the standard PATH
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass
        
        # Check common Windows installation paths
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            os.path.expanduser(r"~\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-*\bin\ffmpeg.exe")
        ]
        
        for path in common_paths:
            if "*" in path:
                # Handle wildcard paths for winget installations
                import glob
                matches = glob.glob(path)
                if matches and os.path.exists(matches[0]):
                    return True
            elif os.path.exists(path):
                return True
        
        return False
        
    async def get_recording_url(self, account_id: str, call_id: str) -> Optional[str]:
        url = f"{CALLRAIL_API_BASE}/a/{account_id}/calls/{call_id}.json"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    print(f"Failed to fetch call details: {response.status}")
                    return None
                data = await response.json()
                recording_url = data.get("recording")
                print(f"Recording URL: {recording_url}")
                return recording_url



    async def download_audio(self, audio_url: str) -> Optional[str]:
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            temp_path = temp_file.name
            temp_file.close()
            async with aiohttp.ClientSession() as session:
                # First request: get the JSON with the real audio URL
                async with session.get(audio_url, headers=headers) as response:
                    content_type = response.headers.get('Content-Type', '')
                    print(f"Download response status: {response.status}")
                    print(f"Download response content-type: {content_type}")
                    if content_type.startswith('application/json'):
                        data = await response.json()
                        real_audio_url = data.get('url')
                        if not real_audio_url:
                            print("No audio URL found in JSON response.")
                            return None
                        # Second request: download the actual audio file
                        async with session.get(real_audio_url) as audio_response:
                            audio_content_type = audio_response.headers.get('Content-Type', '')
                            print(f"Audio file content-type: {audio_content_type}")
                            if not audio_content_type.startswith('audio/'):
                                print(f"Downloaded file is not audio. Content-Type: {audio_content_type}")
                                return None
                            data = await audio_response.read()
                            with open(temp_path, 'wb') as f:
                                f.write(data)
                            print(f"Downloaded {len(data)} bytes to {temp_path}")
                            return temp_path
                    elif content_type.startswith('audio/'):
                        data = await response.read()
                        with open(temp_path, 'wb') as f:
                            f.write(data)
                        print(f"Downloaded {len(data)} bytes to {temp_path}")
                        return temp_path
                    else:
                        print(f"Downloaded file is not audio. Content-Type: {content_type}")
                        return None
        except Exception as e:
            print(f"Error downloading audio: {str(e)}")
            return None

    def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        try:
            if not os.path.exists(audio_path):
                print(f"File not found for transcription: {audio_path}")
                return None
            
            if not self.ffmpeg_available:
                print("FFmpeg not available. Please install FFmpeg to enable audio transcription.")
                print("Install options:")
                print("1. winget install 'FFmpeg (Essentials Build)'")
                print("2. choco install ffmpeg")
                print("3. Download from https://ffmpeg.org/download.html")
                return {
                    'transcription': '[Audio transcription unavailable - FFmpeg not installed]',
                    'language': 'unknown'
                }
            
            print(f"File ready for transcription: {audio_path}")
            result = self.model.transcribe(audio_path)
            return {
                'transcription': result['text'],
                'language': result['language']
            }
        except Exception as e:
            print(f"Error transcribing audio: {str(e)}")
            traceback.print_exc()
            return None
        finally:
            # Only delete if the file still exists
            if os.path.exists(audio_path):
                os.unlink(audio_path)

    async def process_call(self, account_id: str, call_id: str) -> Dict[str, Any]:
        recording_url = await self.get_recording_url(account_id, call_id)
        if not recording_url:
            return {'error': 'Could not get recording URL'}
        audio_path = await self.download_audio(recording_url)
        if not audio_path:
            return {'error': 'Failed to download audio or file is not audio format'}
        transcription_result = self.transcribe_audio(audio_path)
        if not transcription_result:
            return {'error': 'Failed to transcribe audio'}
        return {
            'status': 'success',
            'transcription': transcription_result['transcription'],
            'language': transcription_result['language'],
            'processed_at': datetime.now().isoformat()
        }


