import asyncio
import os
import sys

# Add project root to python path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Mock backend configuration if needed, or import directly
from app.services.chng_dt_poller import _run_poller_async

async def main():
    print("Starting manual run of _run_poller_async...")
    await _run_poller_async()
    print("Done manual run!")

if __name__ == "__main__":
    asyncio.run(main())
