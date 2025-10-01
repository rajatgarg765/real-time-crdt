import asyncio
import websockets

DOC_ID = "test-doc"
SERVER_URL = f"ws://localhost:8000/ws/{DOC_ID}"

async def connect_client(i):
    try:
        async with websockets.connect(SERVER_URL + f"?client_id=client-{i}") as ws:
            await ws.recv()  # receive snapshot
            return True
    except Exception as e:
        print(f"❌ Client {i} failed: {e}")
        return False

async def main():
    max_clients = 5000   # adjust higher if needed
    step = 100           # try 100 clients at a time
    connected = 0

    for batch_start in range(0, max_clients, step):
        tasks = [asyncio.create_task(connect_client(i)) for i in range(batch_start, batch_start + step)]
        results = await asyncio.gather(*tasks)
        success = sum(results)
        connected += success
        print(f"✅ Connected {connected} clients so far")

        if success < step:
            print(f"⚠️ Server refused connections after {connected} clients")
            break

if __name__ == "__main__":
    asyncio.run(main())
