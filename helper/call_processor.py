import os
from typing import Optional, Dict, Any
import tempfile
import aiohttp
from datetime import datetime
import traceback
from dotenv import load_dotenv
import subprocess

# --- ASR engine: faster-whisper ---
from faster_whisper import WhisperModel

# (Optional) for CUDA detection / VAD
try:
    import torch
    _HAS_TORCH = True
except Exception:
    _HAS_TORCH = False

load_dotenv()

CALLRAIL_API_BASE = "https://api.callrail.com/v3"
CALLRAIL_BEARER_TOKEN = os.getenv("CALLRAIL_BEARER_TOKEN")
if not CALLRAIL_BEARER_TOKEN:
    raise ValueError("CALLRAIL_BEARER_TOKEN not found in environment variables")


def _detect_device_and_type():
    """
    Decide device/precision for faster-whisper.
    CUDA GPU → float16, else CPU int8 for speed.
    """
    use_gpu = False
    if _HAS_TORCH:
        try:
            use_gpu = torch.cuda.is_available()
        except Exception:
            use_gpu = False

    if use_gpu:
        return ("cuda", "float16")
    else:
        # Very fast on CPU with quantization
        return ("cpu", "int8")


class CallProcessor:
    def __init__(self):
        self.bearer_token = CALLRAIL_BEARER_TOKEN

        # Initialize faster-whisper model once
        model_name = os.getenv("FASTER_WHISPER_MODEL", "base")
        device, compute_type = _detect_device_and_type()

        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=max(1, os.cpu_count() - 1) if device == "cpu" else 0
        )

        # Check if FFmpeg is available (useful for mp3/m4a decoding)
        self.ffmpeg_available = self._check_ffmpeg()

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available in the system"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass

        # Common Windows paths
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            os.path.expanduser(
                r"~\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-*\bin\ffmpeg.exe"
            ),
        ]
        import glob
        for path in common_paths:
            if "*" in path:
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
                # First request may return JSON pointing to the real audio URL
                async with session.get(audio_url, headers=headers) as response:
                    content_type = response.headers.get('Content-Type', '')

                    if content_type.startswith('application/json'):
                        data = await response.json()
                        real_audio_url = data.get('url')
                        if not real_audio_url:
                            print("No audio URL found in JSON response.")
                            return None
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

    def transcribe_audio(self, audio_path: str) -> Optional[Dict[str, Any]]:
        try:
            if not os.path.exists(audio_path):
                print(f"File not found for transcription: {audio_path}")
                return None

            if not self.ffmpeg_available:
                # faster-whisper can still read some formats; mp3/m4a is safest with ffmpeg.
                print("FFmpeg not available. Some audio formats may fail to decode.")

            print(f"File ready for transcription: {audio_path}")

            # faster-whisper API → returns (segments, info)
            segments, info = self.model.transcribe(
                audio_path,
                beam_size=1,      # greedy (fastest)
                vad_filter=True,  # requires torch; trims silence
                chunk_length=30,  # seconds
                language=None     # or "en" if known
            )

            text = " ".join(seg.text.strip() for seg in segments if getattr(seg, "text", None))
            detected_lang = getattr(info, "language", None) or "unknown"

            return {
                "transcription": text,
                "language": detected_lang
            }
        except Exception as e:
            print(f"Error transcribing audio: {str(e)}")
            traceback.print_exc()
            return None
        finally:
            try:
                if os.path.exists(audio_path):
                    os.unlink(audio_path)
            except Exception:
                pass

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

