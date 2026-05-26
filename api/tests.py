import json
import os
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from unittest import skipUnless

try:
    import rest_framework_simplejwt  # noqa: F401
    SIMPLEJWT_AVAILABLE = True
except Exception:
    SIMPLEJWT_AVAILABLE = False


@skipUnless(SIMPLEJWT_AVAILABLE, "simplejwt dependency not installed")
class AuthApiTests(TestCase):
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


class HealthEndpointTests(TestCase):
    def test_health_live_is_fast_and_alive(self):
        response = self.client.get(reverse("health_live"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "alive")
        self.assertEqual(payload["service"], "academerag-api")

    def test_metrics_endpoint_exposes_counters(self):
        self.client.get(reverse("health_live"))
        response = self.client.get(reverse("metrics"))
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
        response = self.client.get(reverse("health_ready"))
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
        response = self.client.get(reverse("health_ready"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["services"]["vector_store"])
        self.assertTrue(payload["services"]["llm"])


class RetrievalBehaviorTests(TestCase):
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
