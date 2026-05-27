import asyncio
import aiohttp
import time
import argparse
import json

async def make_request(session, url, payload, is_stream=False):
    start_time = time.time()
    ttft = None
    try:
        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            if is_stream:
                async for chunk in response.content.iter_any():
                    if ttft is None:
                        ttft = time.time() - start_time
                # If stream is empty or consumed fully in one go
                if ttft is None:
                    ttft = time.time() - start_time
            else:
                await response.read()
                # For non-stream, TTFT is essentially the total time
                ttft = time.time() - start_time 
            
            total_time = time.time() - start_time
            return {"success": True, "ttft": ttft, "total_time": total_time}
    except Exception as e:
        total_time = time.time() - start_time
        return {"success": False, "ttft": None, "total_time": total_time, "error": str(e)}

async def worker(queue, session, url, payload, is_stream, results):
    while True:
        try:
            _ = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        
        result = await make_request(session, url, payload, is_stream)
        results.append(result)
        queue.task_done()

def print_metrics(name, results):
    success_results = [r for r in results if r["success"]]
    errors = len(results) - len(success_results)
    
    print(f"\n--- Metrics for {name} ---")
    print(f"Total Requests: {len(results)}")
    print(f"Successful: {len(success_results)}")
    print(f"Failed: {errors}")
    
    if not success_results:
        print("No successful requests to calculate metrics.")
        return

    ttft_list = sorted([r["ttft"] for r in success_results])
    total_time_list = sorted([r["total_time"] for r in success_results])
    
    def calc_percentile(data, p):
        idx = int((len(data) - 1) * (p / 100.0))
        return data[idx]
    
    if "/stream/" in name:
        print("\nTime To First Token (TTFT) - Seconds:")
        print(f"  p50: {calc_percentile(ttft_list, 50):.4f}")
        print(f"  p95: {calc_percentile(ttft_list, 95):.4f}")
        print(f"  p99: {calc_percentile(ttft_list, 99):.4f}")
    
    print("\nTotal Response Time - Seconds:")
    print(f"  p50: {calc_percentile(total_time_list, 50):.4f}")
    print(f"  p95: {calc_percentile(total_time_list, 95):.4f}")
    print(f"  p99: {calc_percentile(total_time_list, 99):.4f}")

async def run_load_test(base_url, concurrency, total_requests, payload):
    ask_url = f"{base_url.rstrip('/')}/api/ask/"
    stream_url = f"{base_url.rstrip('/')}/api/ask/stream/"
    
    print(f"Starting load test with concurrency={concurrency}, total_requests={total_requests} per endpoint")
    
    async with aiohttp.ClientSession() as session:
        # Test /api/ask/
        print(f"\nTesting {ask_url} ...")
        ask_queue = asyncio.Queue()
        for i in range(total_requests):
            ask_queue.put_nowait(i)
            
        ask_results = []
        ask_workers = [asyncio.create_task(worker(ask_queue, session, ask_url, payload, False, ask_results)) for _ in range(concurrency)]
        
        await asyncio.gather(*ask_workers)
        print_metrics("/api/ask/", ask_results)
        
        # Test /api/ask/stream/
        print(f"\nTesting {stream_url} ...")
        stream_queue = asyncio.Queue()
        for i in range(total_requests):
            stream_queue.put_nowait(i)
            
        stream_results = []
        stream_workers = [asyncio.create_task(worker(stream_queue, session, stream_url, payload, True, stream_results)) for _ in range(concurrency)]
        
        await asyncio.gather(*stream_workers)
        print_metrics("/api/ask/stream/", stream_results)

def main():
    parser = argparse.ArgumentParser(description="Load testing script for RAG endpoints")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of the API")
    parser.add_argument("-c", "--concurrency", type=int, default=10, help="Number of concurrent users")
    parser.add_argument("-n", "--requests", type=int, default=50, help="Total number of requests per endpoint")
    parser.add_argument("--payload", type=str, default='{"question": "What is RAG?"}', help="JSON payload for the request body")
    
    args = parser.parse_args()
    
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError:
        print("Invalid JSON payload.")
        return
        
    asyncio.run(run_load_test(args.url, args.concurrency, args.requests, payload))

if __name__ == "__main__":
    main()
