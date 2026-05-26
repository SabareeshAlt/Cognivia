import re

def apply_fix():
    with open("Milvus.py", "r", encoding="utf-8") as f:
        content = f.read()

    # The code to inject
    schedule_code = r"""
def _schedule_fallback_cache_refresh(force: bool = False) -> None:
    file_metadata = _collect_pdf_metadata()
    signature = _fallback_signature(file_metadata)
    with _fallback_cache_lock:
        if _fallback_cache_state["inflight"]:
            return
        if not force and _fallback_cache_state["signature"] == signature and _fallback_cache_state["stats"] is not None:
            return
        _fallback_cache_state["inflight"] = True

    def _runner():
        try:
            _refresh_fallback_cache()
        except Exception as exc:
            logger.error("Background local corpus refresh failed: %s", exc)
            with _fallback_cache_lock:
                _fallback_cache_state["inflight"] = False

    threading.Thread(target=_runner, daemon=True).start()

def _wait_for_fallback_cache(max_wait_seconds: float = 2.0) -> None:"""

    # We replace def _wait_for_fallback_cache with schedule_code + def _wait_for_fallback_cache
    content = re.sub(r'def _wait_for_fallback_cache\(max_wait_seconds: float = 2.0\) -> None:', schedule_code, content)

    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    apply_fix()
    print("Fixed missing _schedule_fallback_cache_refresh")
