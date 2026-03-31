import logging
import os
import re
import sys

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP
from simple_salesforce import Salesforce

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("salesforce-mcp")

mcp = FastMCP("salesforce-simple-mcp")

CASE_NUMBER_RE = re.compile(r"^\d{1,10}$")
CASE_NUMBER_WIDTH = 8


# ---------------------------------------------------------------------------
# Auth middleware – checks for a Bearer token matching the MCP_API_KEY env var.
# If MCP_API_KEY is not set, authentication is disabled (open access).
# ---------------------------------------------------------------------------
class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = os.environ.get("MCP_API_KEY")
        if api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header != f"Bearer {api_key}":
                return JSONResponse(
                    {"error": "Unauthorized"}, status_code=401
                )
        return await call_next(request)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Salesforce client
# ---------------------------------------------------------------------------
def get_salesforce_client() -> Salesforce:
    """Create an authenticated Salesforce client from environment variables.

    Supports two auth modes:
    1. Connected App (OAuth Client Credentials): Set SF_CONSUMER_KEY and SF_CONSUMER_SECRET
    2. Username/Password: Set SF_USERNAME, SF_PASSWORD, and SF_SECURITY_TOKEN
    """
    domain = os.environ.get("SF_DOMAIN", "login")

    consumer_key = os.environ.get("SF_CONSUMER_KEY")
    consumer_secret = os.environ.get("SF_CONSUMER_SECRET")

    if consumer_key and consumer_secret:
        logger.info("Authenticating to Salesforce via Connected App (domain=%s)", domain)
        return Salesforce(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            domain=domain,
        )

    missing = [
        var
        for var in ("SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN")
        if not os.environ.get(var)
    ]
    if missing:
        raise RuntimeError(
            f"Salesforce auth not configured. Set SF_CONSUMER_KEY/SF_CONSUMER_SECRET "
            f"for Connected App auth, or set all of SF_USERNAME/SF_PASSWORD/SF_SECURITY_TOKEN "
            f"for username/password auth. Missing: {', '.join(missing)}"
        )

    logger.info("Authenticating to Salesforce via username/password (domain=%s)", domain)
    return Salesforce(
        username=os.environ["SF_USERNAME"],
        password=os.environ["SF_PASSWORD"],
        security_token=os.environ["SF_SECURITY_TOKEN"],
        domain=domain,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def create_case(
    subject: str,
    description: str,
    status: str = "New",
    priority: str = "Medium",
    origin: str = "Web",
    case_type: str | None = None,
    contact_id: str | None = None,
    account_id: str | None = None,
) -> dict:
    """Create a new Case in Salesforce.

    Args:
        subject: Brief summary of the case.
        description: Detailed description of the issue.
        status: Case status (e.g. New, Working, Escalated). Defaults to "New".
        priority: Priority level (Low, Medium, High). Defaults to "Medium".
        origin: How the case originated (Phone, Email, Web). Defaults to "Web".
        case_type: Type of case (Question, Problem, Feature Request).
        contact_id: Salesforce Contact ID to associate with the case.
        account_id: Salesforce Account ID to associate with the case.
    """
    sf = get_salesforce_client()

    case_data = {
        "Subject": subject,
        "Description": description,
        "Status": status,
        "Priority": priority,
        "Origin": origin,
    }

    if case_type:
        case_data["Type"] = case_type
    if contact_id:
        case_data["ContactId"] = contact_id
    if account_id:
        case_data["AccountId"] = account_id

    logger.info("Creating case: subject=%s, priority=%s", subject, priority)
    result = sf.Case.create(case_data)
    logger.info("Case created: %s", result.get("id"))
    return result


@mcp.tool()
def get_case(case_number: str) -> dict:
    """Retrieve a Salesforce Case by its Case Number (e.g. "00001042").

    Args:
        case_number: The Case Number to look up. Can be a plain number like "1042"
            which will be zero-padded to the standard 8-digit format "00001042".
    """
    case_number = case_number.strip()

    if not CASE_NUMBER_RE.match(case_number):
        return {"error": "Invalid case number format. Expected only digits (e.g. '00001042' or '1042')."}

    # Zero-pad to standard 8-digit format
    case_number = case_number.zfill(CASE_NUMBER_WIDTH)

    sf = get_salesforce_client()

    logger.info("Looking up case: %s", case_number)
    result = sf.query(
        f"SELECT Id, CaseNumber, Subject, Description, Status, Priority, Origin "
        f"FROM Case WHERE CaseNumber = '{case_number}' LIMIT 1"
    )

    if result["totalSize"] == 0:
        return {"error": f"No case found with CaseNumber '{case_number}'."}

    return result["records"][0]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "sse").lower()
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))

    if transport == "stdio":
        logger.info("Starting Salesforce MCP server (stdio)...")
        mcp.run(transport="stdio")
    else:
        logger.info("Starting Salesforce MCP server (%s) on %s:%s...", transport, host, port)
        app = Starlette(
            routes=[
                Route("/health", health_check),
                Mount("/", app=mcp.sse_app()),
            ],
            middleware=[
                Middleware(BearerAuthMiddleware),
            ],
        )

        import uvicorn

        uvicorn.run(app, host=host, port=port)
