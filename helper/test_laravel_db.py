# helper/test_laravel_db.py
import sys, asyncio
# ↓ This avoids Proactor quirks with aiomysql on Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from laravel_db import fetch_services, fetch_service_by_id, search_services, shutdown

async def main():
    try:
        rows = await fetch_services(limit=3)
        print("LIST(3):", rows)
        if rows:
            sid = rows[0]["id"]
            one = await fetch_service_by_id(sid)
            print(f"GET({sid}):", one)
        searched = await search_services("clean")
        print("SEARCH('clean') count:", len(searched))
    finally:
        # Dispose the AsyncEngine inside the same event loop
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
