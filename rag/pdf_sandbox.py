import multiprocessing
import traceback
try:
    import magic
except ImportError:
    import sys
    from types import ModuleType
    dummy_magic = ModuleType("magic")
    def from_file(filename, mime=False):
        import mimetypes
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"
    dummy_magic.from_file = from_file
    sys.modules["magic"] = dummy_magic
    import magic
from pypdf import PdfReader
import logging

logger = logging.getLogger(__name__)

def _extract_worker(path: str, result_queue: multiprocessing.Queue):
    """
    Worker function to extract PDF text in an isolated process.
    Chains PyMuPDF (fitz) -> pdfplumber -> pypdf as fallback.
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

        pages = []
        engine_used = None
        
        # 1. Try PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(path)
            temp_pages = []
            for i, page in enumerate(doc):
                text = page.get_text()
                temp_pages.append({"page_number": i + 1, "text": text or ""})
            doc.close()
            total_chars = sum(len(p["text"]) for p in temp_pages)
            if total_chars > 0:
                pages = temp_pages
                engine_used = "pymupdf"
                logger.info(f"Successfully extracted PDF text using PyMuPDF from {path}")
        except Exception as e:
            logger.warning(f"PyMuPDF extraction failed for {path}: {e}")

        # 2. Try pdfplumber as fallback
        if not engine_used:
            try:
                import pdfplumber
                temp_pages = []
                with pdfplumber.open(path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        temp_pages.append({"page_number": i + 1, "text": text or ""})
                total_chars = sum(len(p["text"]) for p in temp_pages)
                if total_chars > 0:
                    pages = temp_pages
                    engine_used = "pdfplumber"
                    logger.info(f"Successfully extracted PDF text using pdfplumber from {path}")
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed for {path}: {e}")

        # 3. Try pypdf as final fallback
        if not engine_used:
            try:
                reader = PdfReader(path)
                temp_pages = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    temp_pages.append({"page_number": i + 1, "text": text or ""})
                total_chars = sum(len(p["text"]) for p in temp_pages)
                pages = temp_pages
                engine_used = "pypdf"
                logger.info(f"Successfully extracted PDF text using pypdf from {path}")
            except Exception as e:
                logger.error(f"pypdf extraction failed for {path}: {e}")
                raise

        total_chars = sum(len(p["text"]) for p in pages)
        page_count = len(pages)
        logger.info(f"Extraction metrics for {path}: Pages={page_count}, Characters={total_chars}, Engine={engine_used}")
        
        result_queue.put({
            "success": True,
            "pages": pages,
            "metrics": {
                "character_count": total_chars,
                "page_count": page_count,
                "engine": engine_used
            }
        })
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
