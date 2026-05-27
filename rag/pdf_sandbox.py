import multiprocessing
import traceback
import magic
from pypdf import PdfReader
import logging

logger = logging.getLogger(__name__)

def _extract_worker(path: str, result_queue: multiprocessing.Queue):
    """
    Worker function to extract PDF text in an isolated process.
    """
    try:
        # Validate magic bytes
        with open(path, 'rb') as f:
            header = f.read(5)
            if header != b'%PDF-':
                result_queue.put({"success": False, "error": f"Invalid magic bytes in {path}"})
                return
                
        # Validate MIME
        mime = magic.from_file(path, mime=True)
        if mime != 'application/pdf':
            result_queue.put({"success": False, "error": f"Invalid MIME type {mime} for {path}"})
            return

        reader = PdfReader(path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append({"page_number": i + 1, "text": text})

        result_queue.put({"success": True, "pages": pages})
    except Exception as e:
        logger.error(f"Error in PDF sandbox for {path}: {traceback.format_exc()}")
        result_queue.put({"success": False, "error": str(e)})


def extract_pdf_text_sandboxed(path: str, timeout: int = 60) -> list[dict]:
    """
    Extracts text from a PDF file in a sandboxed multiprocessing worker.
    Returns a list of dicts: [{"page_number": int, "text": str}, ...].
    Raises RuntimeError if extraction fails or times out.
    """
    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_extract_worker, args=(path, result_queue))
    process.start()
    
    try:
        # Wait for the result with a strict timeout
        result = result_queue.get(timeout=timeout)
        process.join(timeout=1.0)
    except multiprocessing.queues.Empty:
        process.terminate()
        process.join()
        raise RuntimeError(f"PDF extraction timed out after {timeout}s for {path}")
    
    if process.exitcode != 0 and process.exitcode is not None:
        raise RuntimeError(f"PDF extraction worker crashed for {path}")
        
    if not result.get("success"):
        raise RuntimeError(result.get("error", "Unknown sandbox error"))
        
    return result.get("pages", [])
