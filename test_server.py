import os
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

# Prevent server module from connecting to Salesforce on import
os.environ.setdefault("SF_USERNAME", "test")
os.environ.setdefault("SF_PASSWORD", "test")
os.environ.setdefault("SF_SECURITY_TOKEN", "test")

from server import (
    BearerAuthMiddleware,
    create_app,
    get_salesforce_client,
    mcp,
)


@pytest.fixture(scope="session")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
class TestHealthCheck:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_no_auth_required(self, client):
        """Health check should work even when MCP_API_KEY is set."""
        with patch.dict(os.environ, {"MCP_API_KEY": "secret"}):
            resp = client.get("/health")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CORS / OPTIONS preflight
# ---------------------------------------------------------------------------
class TestCORS:
    def test_cors_preflight_returns_200(self, client):
        """CORS preflight requires both Origin and Access-Control-Request-Method."""
        resp = client.options(
            "/mcp",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200

    def test_cors_headers_present(self, client):
        resp = client.options(
            "/mcp",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


# ---------------------------------------------------------------------------
# Bearer auth middleware
# ---------------------------------------------------------------------------
class TestBearerAuth:
    def test_no_api_key_allows_all(self, client):
        """When MCP_API_KEY is not set, all requests pass through."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MCP_API_KEY", None)
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_valid_bearer_token(self, client):
        with patch.dict(os.environ, {"MCP_API_KEY": "my-secret"}):
            resp = client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer my-secret",
                    "Content-Type": "application/json",
                },
                json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            )
            # Should not be 401
            assert resp.status_code != 401

    def test_invalid_bearer_token(self, client):
        with patch.dict(os.environ, {"MCP_API_KEY": "my-secret"}):
            resp = client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer wrong-token",
                    "Content-Type": "application/json",
                },
                json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            )
            assert resp.status_code == 401
            assert resp.json() == {"error": "Unauthorized"}

    def test_missing_bearer_token(self, client):
        with patch.dict(os.environ, {"MCP_API_KEY": "my-secret"}):
            resp = client.post(
                "/mcp",
                headers={"Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            )
            assert resp.status_code == 401

    def test_options_skips_auth(self, client):
        """CORS preflight should bypass auth even with MCP_API_KEY set."""
        with patch.dict(os.environ, {"MCP_API_KEY": "my-secret"}):
            resp = client.options(
                "/mcp",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Streamable HTTP endpoint (/mcp)
# ---------------------------------------------------------------------------
class TestMCPEndpoint:
    def test_mcp_post_accepts_jsonrpc(self, client):
        """POST /mcp should accept JSON-RPC requests (not return 404/405)."""
        resp = client.post(
            "/mcp",
            headers={"Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 1,
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
        )
        # Should get a valid response, not 404 or 405
        assert resp.status_code != 404
        assert resp.status_code != 405

    def test_mcp_get_not_allowed(self, client):
        """GET /mcp is not a valid method for streamable HTTP."""
        resp = client.get("/mcp")
        # Streamable HTTP only accepts POST/DELETE, GET returns an error
        assert resp.status_code in (405, 406)


# ---------------------------------------------------------------------------
# Salesforce client factory
# ---------------------------------------------------------------------------
class TestGetSalesforceClient:
    def test_missing_all_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="Salesforce auth not configured"):
                get_salesforce_client()

    def test_missing_partial_credentials(self):
        with patch.dict(
            os.environ,
            {"SF_USERNAME": "user", "SF_PASSWORD": "pass"},
            clear=True,
        ):
            with pytest.raises(RuntimeError, match="SF_SECURITY_TOKEN"):
                get_salesforce_client()

    @patch("server.Salesforce")
    def test_username_password_auth(self, mock_sf):
        with patch.dict(
            os.environ,
            {
                "SF_USERNAME": "user",
                "SF_PASSWORD": "pass",
                "SF_SECURITY_TOKEN": "token",
            },
            clear=True,
        ):
            get_salesforce_client()
            mock_sf.assert_called_once_with(
                username="user",
                password="pass",
                security_token="token",
                domain="login",
            )

    @patch("server.Salesforce")
    def test_connected_app_auth(self, mock_sf):
        with patch.dict(
            os.environ,
            {"SF_CONSUMER_KEY": "key", "SF_CONSUMER_SECRET": "secret"},
            clear=True,
        ):
            get_salesforce_client()
            mock_sf.assert_called_once_with(
                consumer_key="key",
                consumer_secret="secret",
                domain="login",
            )

    @patch("server.Salesforce")
    def test_custom_domain(self, mock_sf):
        with patch.dict(
            os.environ,
            {
                "SF_CONSUMER_KEY": "key",
                "SF_CONSUMER_SECRET": "secret",
                "SF_DOMAIN": "test",
            },
            clear=True,
        ):
            get_salesforce_client()
            mock_sf.assert_called_once_with(
                consumer_key="key",
                consumer_secret="secret",
                domain="test",
            )


# ---------------------------------------------------------------------------
# MCP tools (unit tests with mocked Salesforce)
# ---------------------------------------------------------------------------
class TestCreateCaseTool:
    @patch("server.get_salesforce_client")
    def test_create_case_minimal(self, mock_get_sf):
        mock_sf = MagicMock()
        mock_sf.Case.create.return_value = {"id": "500xx000000001", "success": True}
        mock_get_sf.return_value = mock_sf

        from server import create_case

        result = create_case(subject="Test", description="A test case")
        assert result["id"] == "500xx000000001"
        mock_sf.Case.create.assert_called_once_with(
            {
                "Subject": "Test",
                "Description": "A test case",
                "Status": "New",
                "Priority": "Medium",
                "Origin": "Web",
            }
        )

    @patch("server.get_salesforce_client")
    def test_create_case_all_fields(self, mock_get_sf):
        mock_sf = MagicMock()
        mock_sf.Case.create.return_value = {"id": "500xx000000002", "success": True}
        mock_get_sf.return_value = mock_sf

        from server import create_case

        result = create_case(
            subject="Full case",
            description="All fields",
            status="Escalated",
            priority="High",
            origin="Phone",
            case_type="Problem",
            contact_id="003xx000000001",
            account_id="001xx000000001",
        )
        assert result["success"] is True
        call_data = mock_sf.Case.create.call_args[0][0]
        assert call_data["Type"] == "Problem"
        assert call_data["ContactId"] == "003xx000000001"
        assert call_data["AccountId"] == "001xx000000001"


class TestGetCaseTool:
    @patch("server.get_salesforce_client")
    def test_get_case_found(self, mock_get_sf):
        mock_sf = MagicMock()
        mock_sf.query.return_value = {
            "totalSize": 1,
            "records": [{"Id": "500xx", "CaseNumber": "00001042", "Subject": "Test"}],
        }
        mock_get_sf.return_value = mock_sf

        from server import get_case

        result = get_case("1042")
        assert result["CaseNumber"] == "00001042"
        # Verify zero-padding in query
        query_arg = mock_sf.query.call_args[0][0]
        assert "00001042" in query_arg

    @patch("server.get_salesforce_client")
    def test_get_case_not_found(self, mock_get_sf):
        mock_sf = MagicMock()
        mock_sf.query.return_value = {"totalSize": 0, "records": []}
        mock_get_sf.return_value = mock_sf

        from server import get_case

        result = get_case("99999999")
        assert "error" in result

    def test_get_case_invalid_format(self):
        from server import get_case

        result = get_case("abc")
        assert "error" in result
        assert "Invalid case number" in result["error"]

    def test_get_case_zero_padding(self):
        """Verify case numbers get zero-padded to 8 digits."""
        from server import get_case

        with patch("server.get_salesforce_client") as mock_get_sf:
            mock_sf = MagicMock()
            mock_sf.query.return_value = {"totalSize": 0, "records": []}
            mock_get_sf.return_value = mock_sf

            get_case("42")
            query_arg = mock_sf.query.call_args[0][0]
            assert "00000042" in query_arg
