import asyncio
from helper.transcription_helper import process_unprocessed_callrails

if __name__ == "__main__":
    asyncio.run(process_unprocessed_callrails())
    