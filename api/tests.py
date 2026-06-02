import json
import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from unittest import skipUnless
from django.core.cache import cache

try:
    import rest_framework_simplejwt  # noqa: F401
    SIMPLEJWT_AVAILABLE = True
except Exception:
    SIMPLEJWT_AVAILABLE = False


@skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
class AuthApiTests(TestCase):
    def setUp(self):
        cache.clear()
    def test_register_and_login(self):
        register_resp = self.client.post(
            reverse("auth_register"),
            data=json.dumps({"email": "alice@example.com", "password": "Secure123!", "name": "Alice"}),
            content_type="application/json",
        )
        self.assertEqual(register_resp.status_code, 201)
        payload = register_resp.json()
        self.assertTrue(payload["success"])
        self.assertIn("tokens", payload)
        self.assertIn("access", payload["tokens"])

        login_resp = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "alice@example.com", "password": "Secure123!"}),
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, 200)
        login_payload = login_resp.json()
        self.assertTrue(login_payload["success"])
        self.assertEqual(login_payload["user"]["email"], "alice@example.com")

    def test_auth_me_requires_token(self):
        response = self.client.get(reverse("auth_me"))
        self.assertEqual(response.status_code, 401)
        self.assertIn("trace_id", response.json())

    def test_login_invalid_credentials_has_trace_id(self):
        response = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "missing@example.com", "password": "bad-pass"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("trace_id", response.json())

    def test_register_invalid_json_has_trace_id(self):
        response = self.client.post(
            reverse("auth_register"),
            data="{bad json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("trace_id", response.json())

    @skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
    def test_refresh_rotates_refresh_token(self):
        self.client.post(
            reverse("auth_register"),
            data=json.dumps({"email": "rotate@example.com", "password": "Secure123!", "name": "Rotate"}),
            content_type="application/json",
        )
        login_resp = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "rotate@example.com", "password": "Secure123!"}),
            content_type="application/json",
        )
        old_refresh = login_resp.json()["tokens"]["refresh"]
        refresh_resp = self.client.post(
            reverse("auth_refresh"),
            data=json.dumps({"refresh": old_refresh}),
            content_type="application/json",
        )
        self.assertEqual(refresh_resp.status_code, 200)
        payload = refresh_resp.json()
        self.assertIn("trace_id", payload)
        self.assertNotEqual(payload["tokens"]["refresh"], old_refresh)


class AskEndpointSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
    def test_ask_requires_authentication(self):
        response = self.client.post(
            reverse("ask_question"),
            data=json.dumps({"question": "What is RAG?"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, [401, 503])

    @skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
    def test_ask_validates_payload(self):
        self.client.post(
            reverse("auth_register"),
            data=json.dumps({"email": "bob@example.com", "password": "Secure123!", "name": "Bob"}),
            content_type="application/json",
        )
        login_resp = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "bob@example.com", "password": "Secure123!"}),
            content_type="application/json",
        )
        access_token = login_resp.json()["tokens"]["access"]

        response = self.client.post(
            reverse("ask_question"),
            data=json.dumps({"question": ""}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No question provided", response.json()["error"])


@skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
class HealthEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(
            reverse("auth_register"),
            data=json.dumps({"email": "health@example.com", "password": "Secure123!", "name": "Health"}),
            content_type="application/json",
        )
        login_resp = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "health@example.com", "password": "Secure123!"}),
            content_type="application/json",
        )
        self.token = login_resp.json()["tokens"]["access"]

    def test_health_live_is_fast_and_alive(self):
        response = self.client.get(reverse("health_live"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "alive")
        self.assertEqual(payload["service"], "academerag-api")
        self.assertNotIn("audit", payload)
        self.assertNotIn("audit_error", payload)

    def test_metrics_endpoint_exposes_counters(self):
        self.client.get(reverse("health_live"))
        response = self.client.get(reverse("metrics"), HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("academerag_http_requests_total", body)

    @patch("api.views._load_rag_modules")
    @patch("api.views._vector_store_fn", autospec=False)
    @patch("requests.get")
    def test_health_ready_degraded_when_vector_unavailable(self, mock_requests_get, mock_vector_store_fn, mock_loader):
        mock_loader.return_value = None
        mock_vector_store_fn.return_value = None
        mock_requests_get.side_effect = Exception("dependency down")
        from api import views as api_views
        api_views._vector_ready_cache["ready"] = False
        api_views._vector_ready_cache["last_error"] = "unavailable"
        response = self.client.get(reverse("health_ready"), HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertFalse(payload["services"]["vector_store"])

    @patch("api.views._load_rag_modules")
    @patch("api.views._vector_store_fn", autospec=False)
    @patch("requests.get")
    def test_health_ready_healthy_when_dependencies_available(self, mock_requests_get, mock_vector_store_fn, mock_loader):
        mock_loader.return_value = None
        mock_vector_store_fn.return_value = object()
        mock_requests_get.return_value.status_code = 200
        from api import views as api_views
        api_views._vector_ready_cache["ready"] = True
        api_views._vector_ready_cache["last_error"] = None
        response = self.client.get(reverse("health_ready"), HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["services"]["vector_store"])
        self.assertTrue(payload["services"]["llm"])


class RetrievalBehaviorTests(TestCase):
    def setUp(self):
        cache.clear()
    @skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
    @patch("api.views._load_rag_modules")
    @patch("api.views._response_fn", autospec=False)
    def test_ask_returns_deterministic_empty_index_message(self, mock_response_fn, mock_loader):
        mock_loader.return_value = None
        mock_response_fn.return_value = (
            "I am not trained on this data source or the uploaded documents do not contain this information."
        )
        self.client.post(
            reverse("auth_register"),
            data=json.dumps({"email": "deterministic@example.com", "password": "Secure123!", "name": "Deterministic"}),
            content_type="application/json",
        )
        login_resp = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "deterministic@example.com", "password": "Secure123!"}),
            content_type="application/json",
        )
        access_token = login_resp.json()["tokens"]["access"]
        response = self.client.post(
            reverse("ask_question"),
            data=json.dumps({"question": "What is unavailable?"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("I am not trained on this data source", payload["answer"])

    @skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
    def test_retrieval_diagnostics_requires_admin(self):
        self.client.post(
            reverse("auth_register"),
            data=json.dumps({"email": "diag@example.com", "password": "Secure123!", "name": "Diag"}),
            content_type="application/json",
        )
        login_resp = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "diag@example.com", "password": "Secure123!"}),
            content_type="application/json",
        )
        access_token = login_resp.json()["tokens"]["access"]
        response = self.client.get(
            reverse("retrieval_diagnostics"),
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("trace_id", response.json())

@skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
class DependencyFailureTests(TestCase):
    def setUp(self):
        cache.clear()
    def _auth_header(self) -> str:
        self.client.post(
            reverse("auth_register"),
            data=json.dumps({"email": "dep@example.com", "password": "Secure123!", "name": "Dep"}),
            content_type="application/json",
        )
        login_resp = self.client.post(
            reverse("auth_login"),
            data=json.dumps({"email": "dep@example.com", "password": "Secure123!"}),
            content_type="application/json",
        )
        return f"Bearer {login_resp.json()['tokens']['access']}"

    @patch("api.views._load_rag_modules")
    @patch("api.views._response_fn", autospec=False)
    def test_ask_returns_503_when_llm_connection_refused(self, mock_response_fn, mock_loader):
        mock_loader.return_value = None
        mock_response_fn.side_effect = RuntimeError("[WinError 10061] No connection could be made because the target machine actively refused it")

        response = self.client.post(
            reverse("ask_question"),
            data=json.dumps({"question": "Test question"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth_header(),
        )

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertIn("LLM dependency is unreachable", payload["error"])
        self.assertIn("trace_id", payload)

    @patch("api.views._load_rag_modules")
    @patch("api.views._response_fn", autospec=False)
    def test_ask_hides_internal_error_details(self, mock_response_fn, mock_loader):
        mock_loader.return_value = None
        mock_response_fn.side_effect = RuntimeError("Sensitive internal stack details")

        response = self.client.post(
            reverse("ask_question"),
            data=json.dumps({"question": "Test question"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=self._auth_header(),
        )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"], "Failed to process the question due to an internal dependency error.")
        self.assertNotIn("Sensitive internal stack details", payload["error"])


class CitationCleaningTests(TestCase):
    def test_clean_citations_removes_placeholders(self):
        from rag.llm_orchestration import clean_citations
        
        # Test 1: Placeholder files are removed
        self.assertEqual(clean_citations("Hello [Source: RAG sample .pdf, Page ] world"), "Hello world")
        self.assertEqual(clean_citations("Hello [Source: RAG sample .pdf, Page: ] world"), "Hello world")
        self.assertEqual(clean_citations("Hello [Source: RAG sample .pdf] world"), "Hello world")
        self.assertEqual(clean_citations("Hello [Source: RAG sample.pdf] world"), "Hello world")
        self.assertEqual(clean_citations("Hello [Source: RAG sample   .pdf, Page 12] world"), "Hello world")
        
        # Test 2: Valid citations are kept
        self.assertEqual(clean_citations("Hello [Source: RAG sample 1.pdf, Page 12] world"), "Hello [Source: RAG sample 1.pdf, Page 12] world")
        self.assertEqual(clean_citations("Hello [Source: RAG sample 2.pdf] world"), "Hello [Source: RAG sample 2.pdf] world")
        self.assertEqual(clean_citations("Hello [Source: course_info.pdf, Page: 45] world"), "Hello [Source: course_info.pdf, Page: 45] world")
        
        # Test 3: Malformed page numbers are removed
        self.assertEqual(clean_citations("Hello [Source: course_info.pdf, Page ] world"), "Hello world")
        self.assertEqual(clean_citations("Hello [Source: course_info.pdf, Page abc] world"), "Hello world")
        self.assertEqual(clean_citations("Hello [Source: , Page 12] world"), "Hello world")


# ---------------------------------------------------------------------------
# Resiliency test suite: Django-cache circuit breaker & recovery
# ---------------------------------------------------------------------------

class CircuitBreakerCacheStateTests(TestCase):
    """Validates CLOSED -> OPEN -> HALF_OPEN -> CLOSED state transitions."""

    def setUp(self):
        cache.clear()

    def test_initial_state_is_closed(self):
        from database.milvus_client import _get_cb_state, _CB_CLOSED
        self.assertEqual(_get_cb_state(), _CB_CLOSED)

    def test_two_failures_open_circuit(self):
        from database.milvus_client import (
            _handle_cloud_failure, _get_cb_state,
            _CB_OPEN, _CB_FAILURE_THRESHOLD,
        )
        exc = RuntimeError("connection refused")
        for _ in range(_CB_FAILURE_THRESHOLD):
            _handle_cloud_failure(exc)
        self.assertEqual(_get_cb_state(), _CB_OPEN)

    def test_open_circuit_transitions_to_half_open_after_ttl(self):
        """Simulate TTL expiry by manually deleting the OPEN state key."""
        from database.milvus_client import (
            _CB_STATE_KEY, _CB_FAILURES_KEY, _CB_FAILURE_THRESHOLD,
            _CB_OPEN, _CB_HALF_OPEN,
            _transition_to_half_open_if_needed, _cache_set, _cache_get,
        )
        # Set up the OPEN state manually
        _cache_set(_CB_STATE_KEY, _CB_OPEN)
        _cache_set(_CB_FAILURES_KEY, _CB_FAILURE_THRESHOLD)

        # Simulate TTL expiry: delete the OPEN key (as Django cache would after timeout)
        from django.core.cache import cache as djcache
        djcache.delete(_CB_STATE_KEY)

        # Now _get_cb_state returns CLOSED (default); transition logic should detect
        # that failures >= threshold and move to HALF_OPEN
        result = _transition_to_half_open_if_needed()
        self.assertTrue(result)
        from database.milvus_client import _get_cb_state
        self.assertEqual(_get_cb_state(), _CB_HALF_OPEN)

    def test_half_open_failure_reopens_circuit(self):
        from database.milvus_client import (
            _CB_STATE_KEY, _CB_HALF_OPEN, _CB_OPEN,
            _handle_cloud_failure, _get_cb_state, _cache_set,
        )
        _cache_set(_CB_STATE_KEY, _CB_HALF_OPEN)
        _handle_cloud_failure(RuntimeError("probe failed"))
        self.assertEqual(_get_cb_state(), _CB_OPEN)

    def test_cloud_circuit_open_returns_true_when_open(self):
        from database.milvus_client import (
            _CB_STATE_KEY, _CB_OPEN, _cloud_circuit_open, _cache_set,
        )
        _cache_set(_CB_STATE_KEY, _CB_OPEN)
        self.assertTrue(_cloud_circuit_open())

    def test_cloud_circuit_open_returns_false_when_closed(self):
        from database.milvus_client import _cloud_circuit_open, _CB_STATE_KEY, _CB_CLOSED, _cache_set
        _cache_set(_CB_STATE_KEY, _CB_CLOSED)
        self.assertFalse(_cloud_circuit_open())


class ControlledRecoveryTests(TestCase):
    """Asserts HALF_OPEN -> CLOSED requires exactly 3 consecutive successes."""

    def setUp(self):
        cache.clear()

    def test_single_success_does_not_close_circuit(self):
        from database.milvus_client import (
            _CB_STATE_KEY, _CB_HALF_OPEN, _CB_CLOSED,
            _handle_cloud_success, _get_cb_state, _cache_set,
        )
        _cache_set(_CB_STATE_KEY, _CB_HALF_OPEN)
        _handle_cloud_success()
        self.assertNotEqual(_get_cb_state(), _CB_CLOSED)

    def test_two_successes_do_not_close_circuit(self):
        from database.milvus_client import (
            _CB_STATE_KEY, _CB_HALF_OPEN, _CB_CLOSED,
            _handle_cloud_success, _get_cb_state, _cache_set,
        )
        _cache_set(_CB_STATE_KEY, _CB_HALF_OPEN)
        _handle_cloud_success()
        _handle_cloud_success()
        self.assertNotEqual(_get_cb_state(), _CB_CLOSED)

    def test_three_successes_close_circuit(self):
        from database.milvus_client import (
            _CB_STATE_KEY, _CB_HALF_OPEN, _CB_CLOSED,
            _handle_cloud_success, _get_cb_state, _cache_set,
        )
        _cache_set(_CB_STATE_KEY, _CB_HALF_OPEN)
        _handle_cloud_success()
        _handle_cloud_success()
        _handle_cloud_success()
        self.assertEqual(_get_cb_state(), _CB_CLOSED)

    def test_failure_mid_recovery_resets_success_count(self):
        from database.milvus_client import (
            _CB_STATE_KEY, _CB_SUCCESSES_KEY, _CB_HALF_OPEN, _CB_OPEN,
            _handle_cloud_success, _handle_cloud_failure,
            _get_cb_state, _cache_get, _cache_set,
        )
        _cache_set(_CB_STATE_KEY, _CB_HALF_OPEN)
        _handle_cloud_success()
        _handle_cloud_success()
        # 2 successes, then a failure — should reopen and reset counter
        _handle_cloud_failure(RuntimeError("intermittent failure"))
        self.assertEqual(_get_cb_state(), _CB_OPEN)
        self.assertEqual(_cache_get(_CB_SUCCESSES_KEY, 0), 0)


class RetrievalFailoverLatencyTests(TestCase):
    """Asserts that failing over to local Milvus when cloud is offline is fast."""

    def setUp(self):
        cache.clear()

    @patch("database.retrieval._search_cloud_milvus", return_value=[])
    @patch("database.retrieval._search_local_milvus", return_value=[])
    @patch("database.retrieval.get_embeddings")
    def test_failover_latency_under_500ms(self, mock_embeddings, mock_local, mock_cloud):
        """Dense pipeline with cloud returning [] should fall back to local under 500ms."""
        import time
        mock_embeddings.return_value.embed_query.return_value = [0.1] * 1024

        from database.retrieval import _dense_search_pipeline
        start = time.perf_counter()
        _dense_search_pipeline("test failover query", k=5, target_sources=None)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertLess(elapsed_ms, 500, f"Failover took {elapsed_ms:.1f}ms, expected < 500ms")
        mock_cloud.assert_called_once()
        mock_local.assert_called_once()


class MetadataVerificationTests(TestCase):
    """Verifies that metadata checks use collection stats, not row scans."""

    def setUp(self):
        cache.clear()

    @patch("database.milvus_client._connect_milvus_client_with_timeout")
    @patch("database.milvus_client._milvus_endpoint_reachable", return_value=False)
    def test_metadata_check_skips_cloud_when_unreachable(self, mock_reachable, mock_connect):
        """When cloud is unreachable, only local stats are queried."""
        from database.milvus_client import check_and_log_metadata_discrepancies

        mock_client = mock_connect.return_value
        mock_client.get_collection_stats.return_value = {"row_count": 5600}

        # Should not raise even if cloud is unreachable
        check_and_log_metadata_discrepancies()

        # Cloud reachability was checked
        mock_reachable.assert_called()
        # Only local client was connected (cloud skipped due to unreachable)
        self.assertEqual(mock_connect.call_count, 1)

    @patch("database.milvus_client._connect_milvus_client_with_timeout")
    @patch("database.milvus_client._milvus_endpoint_reachable", return_value=True)
    @patch("database.milvus_client._get_cloud_config")
    def test_metadata_uses_get_collection_stats_not_query(self, mock_cloud_cfg, mock_reachable, mock_connect):
        """Ensure stats are retrieved via get_collection_stats, not search/query scans."""
        from database.milvus_client import check_and_log_metadata_discrepancies

        mock_cloud_cfg.return_value = {
            "uri": "https://cloud.example.com",
            "token": "tok",
            "collection": "AcademeRAG",
            "model": "bge-m3:latest",
        }
        mock_client = mock_connect.return_value
        mock_client.get_collection_stats.return_value = {"row_count": 5600}

        check_and_log_metadata_discrepancies()

        # get_collection_stats must be called, never search or query
        self.assertTrue(mock_client.get_collection_stats.called)
        self.assertFalse(mock_client.search.called if hasattr(mock_client, "search") else False)
        self.assertFalse(mock_client.query.called if hasattr(mock_client, "query") else False)


