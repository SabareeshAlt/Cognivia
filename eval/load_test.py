import asyncio
import aiohttp
import time
import argparse
import json
import sys

async def make_request(session, url, payload, is_stream=False):
    start_time = time.time()
    ttft = None
    token_count = 0
    try:
        async with session.post(url, json=payload) as response:
            if response.status == 429:
                return {"success": False, "ttft": None, "total_time": time.time() - start_time, "error": "Rate Limited (429)", "token_count": 0, "status": 429}
            
            response.raise_for_status()
            if is_stream:
                async for line in response.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith('data: '):
                        if ttft is None:
                            ttft = time.time() - start_time
                        
                        try:
                            data = json.loads(line_str[6:])
                            if data.get('type') == 'token':
                                token_count += 1
                        except json.JSONDecodeError:
                            token_count += 1
                
                if ttft is None:
                    ttft = time.time() - start_time
            else:
                await response.read()
                ttft = time.time() - start_time 
            
            total_time = time.time() - start_time
            return {"success": True, "ttft": ttft, "total_time": total_time, "token_count": token_count, "status": response.status}
    except Exception as e:
        total_time = time.time() - start_time
        return {"success": False, "ttft": None, "total_time": total_time, "error": str(e), "token_count": 0, "status": 500}

async def worker(queue, session, url, payload, is_stream, results):
    while True:
        try:
            _ = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        
        result = await make_request(session, url, payload, is_stream)
        results.append(result)
        queue.task_done()

def print_metrics(name, results, target_ttft, target_tps, target_success_rate):
    success_results = [r for r in results if r["success"]]
    errors = len(results) - len(success_results)
    
    rate_limited = len([r for r in results if r.get("status") == 429])
    
    print(f"\n--- Metrics for {name} ---")
    print(f"Total Requests: {len(results)}")
    print(f"Successful: {len(success_results)}")
    print(f"Failed: {errors} (Rate Limited: {rate_limited})")
    
    success_rate = len(success_results) / len(results) if results else 0
    print(f"Success Rate: {success_rate * 100:.2f}%")
    
    assertion_failed = False
    
    if success_rate < target_success_rate:
        print(f"❌ ASSERTION FAILED: Success rate ({success_rate * 100:.2f}%) < Target ({target_success_rate * 100:.2f}%)")
        assertion_failed = True
    else:
        print(f"✅ ASSERTION PASSED: Success rate ({success_rate * 100:.2f}%) >= Target ({target_success_rate * 100:.2f}%)")
    
    if not success_results:
        print("No successful requests to calculate timing metrics.")
        return not assertion_failed

    ttft_list = sorted([r["ttft"] for r in success_results if r["ttft"] is not None])
    total_time_list = sorted([r["total_time"] for r in success_results])
    
    def calc_percentile(data, p):
        if not data:
            return 0.0
        idx = int((len(data) - 1) * (p / 100.0))
        return data[idx]
    
    if "/stream/" in name:
        print("\nTime To First Token (TTFT) - Seconds:")
        print(f"  p50: {calc_percentile(ttft_list, 50):.4f}")
        print(f"  p95: {calc_percentile(ttft_list, 95):.4f}")
        print(f"  p99: {calc_percentile(ttft_list, 99):.4f}")
        
        tps_list = []
        for r in success_results:
            duration = r["total_time"] - r["ttft"]
            if duration > 0 and r.get("token_count", 0) > 0:
                tps_list.append(r["token_count"] / duration)
        
        if tps_list:
            tps_list.sort()
            print("\nTokens Per Second (TPS) - Per Request:")
            print(f"  p50: {calc_percentile(tps_list, 50):.2f}")
            print(f"  p95: {calc_percentile(tps_list, 95):.2f}")
            print(f"  p99: {calc_percentile(tps_list, 99):.2f}")

            p50_tps = calc_percentile(tps_list, 50)
            if p50_tps < target_tps:
                print(f"❌ ASSERTION FAILED: p50 TPS ({p50_tps:.2f}) < Target ({target_tps})")
                assertion_failed = True
            else:
                print(f"✅ ASSERTION PASSED: p50 TPS ({p50_tps:.2f}) >= Target ({target_tps})")
                
        p95_ttft = calc_percentile(ttft_list, 95)
        if p95_ttft > target_ttft:
            print(f"❌ ASSERTION FAILED: p95 TTFT ({p95_ttft:.4f}s) > Target ({target_ttft}s)")
            assertion_failed = True
        else:
            print(f"✅ ASSERTION PASSED: p95 TTFT ({p95_ttft:.4f}s) <= Target ({target_ttft}s)")
    
    print("\nTotal Response Time - Seconds:")
    print(f"  p50: {calc_percentile(total_time_list, 50):.4f}")
    print(f"  p95: {calc_percentile(total_time_list, 95):.4f}")
    print(f"  p99: {calc_percentile(total_time_list, 99):.4f}")
    
    return not assertion_failed

async def run_load_test(base_url, concurrency, total_requests, payload, target_ttft, target_tps, target_success_rate):
    ask_url = f"{base_url.rstrip('/')}/api/ask/"
    stream_url = f"{base_url.rstrip('/')}/api/ask/stream/"
    
    print(f"Starting load test targeting local offline Docker stack")
    print(f"Concurrency: {concurrency}, Total Requests: {total_requests} per endpoint")
    print(f"Targets - TTFT: <={target_ttft}s, TPS: >={target_tps}, Success Rate: >={target_success_rate*100}%")
    
    all_passed = True
    
    timeout = aiohttp.ClientTimeout(total=300) # 5 minutes max per request
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Test /api/ask/
        print(f"\nTesting {ask_url} ...")
        ask_queue = asyncio.Queue()
        for i in range(total_requests):
            ask_queue.put_nowait(i)
            
        ask_results = []
        ask_workers = [asyncio.create_task(worker(ask_queue, session, ask_url, payload, False, ask_results)) for _ in range(concurrency)]
        
        await asyncio.gather(*ask_workers)
        if not print_metrics("/api/ask/", ask_results, target_ttft, target_tps, target_success_rate):
            all_passed = False
        
        # Test /api/ask/stream/
        print(f"\nTesting {stream_url} ...")
        stream_queue = asyncio.Queue()
        for i in range(total_requests):
            stream_queue.put_nowait(i)
            
        stream_results = []
        stream_workers = [asyncio.create_task(worker(stream_queue, session, stream_url, payload, True, stream_results)) for _ in range(concurrency)]
        
        await asyncio.gather(*stream_workers)
        if not print_metrics("/api/ask/stream/", stream_results, target_ttft, target_tps, target_success_rate):
            all_passed = False
            
    if not all_passed:
        print("\n❌ SOME ASSERTIONS FAILED.")
        sys.exit(1)
    else:
        print("\n✅ ALL ASSERTIONS PASSED.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Load testing script for local offline Docker stack")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the API")
    parser.add_argument("-c", "--concurrency", type=int, default=10, help="Number of concurrent users")
    parser.add_argument("-n", "--requests", type=int, default=50, help="Total number of requests per endpoint")
    parser.add_argument("--payload", type=str, default='{"question": "What is RAG?"}', help="JSON payload for the request body")
    
    parser.add_argument("--target-ttft", type=float, default=2.0, help="Target p95 TTFT in seconds")
    parser.add_argument("--target-tps", type=float, default=10.0, help="Target p50 Tokens/Sec")
    parser.add_argument("--target-success-rate", type=float, default=0.95, help="Target success rate (0.0 to 1.0)")
    
    args = parser.parse_args()
    
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError:
        print("Invalid JSON payload.")
        sys.exit(1)
        
    asyncio.run(run_load_test(args.url, args.concurrency, args.requests, payload, args.target_ttft, args.target_tps, args.target_success_rate))

if __name__ == "__main__":
    main()
