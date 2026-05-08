"""
Twitter/X OAuth 2.0 PKCE Authorization Flow
Run this script, it opens browser for login, then saves access token to .env
"""
import os
import json
import hashlib
import base64
import secrets
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse
from urllib.request import Request, urlopen
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ.get("TWITTER_CLIENT_ID", "MlBBWjBPbkd6c1JoSHZIcjNEUUo6MTpjaQ")
REDIRECT_URI = "http://localhost:3333/callback"
SCOPES = "tweet.read tweet.write users.read offline.access"

# PKCE
code_verifier = secrets.token_urlsafe(64)[:128]
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).decode().rstrip("=")
state = secrets.token_urlsafe(16)

auth_url = (
    "https://twitter.com/i/oauth2/authorize?"
    + urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
)

received_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global received_code
        qs = parse_qs(urlparse(self.path).query)
        received_code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Done! You can close this tab.</h1>")

    def log_message(self, format, *args):
        pass

print("Opening browser for Twitter authorization...")
print(f"\nIf browser doesn't open, go to:\n{auth_url}\n")
webbrowser.open(auth_url)

server = HTTPServer(("localhost", 3333), CallbackHandler)
print("Waiting for authorization...")
server.handle_request()
server.server_close()

if not received_code:
    print("ERROR: No authorization code received")
    exit(1)

print(f"Got auth code. Exchanging for token...")

# Exchange code for token
client_secret = os.environ.get("TWITTER_CLIENT_SECRET")
if not client_secret:
    print("ERROR: set TWITTER_CLIENT_SECRET in env (do not hardcode).")
    exit(1)
token_data = urlencode({
    "code": received_code,
    "grant_type": "authorization_code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "code_verifier": code_verifier,
}).encode()

creds = base64.b64encode(f"{CLIENT_ID}:{client_secret}".encode()).decode()
req = Request("https://api.twitter.com/2/oauth2/token", data=token_data, method="POST")
req.add_header("Content-Type", "application/x-www-form-urlencoded")
req.add_header("Authorization", f"Basic {creds}")

with urlopen(req, timeout=15) as resp:
    tokens = json.loads(resp.read())

access_token = tokens["access_token"]
refresh_token = tokens.get("refresh_token", "")

print(f"\nAccess Token: {access_token[:20]}...")
print(f"Refresh Token: {refresh_token[:20] if refresh_token else 'none'}...")

# Save to .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
with open(env_path, "r") as f:
    content = f.read()

# Add or update tokens
for key, val in [("TWITTER_OAUTH2_TOKEN", access_token), ("TWITTER_REFRESH_TOKEN", refresh_token), ("TWITTER_CLIENT_ID", CLIENT_ID), ("TWITTER_CLIENT_SECRET", client_secret)]:
    if f"{key}=" in content:
        lines = content.split("\n")
        content = "\n".join(
            f"{key}={val}" if line.startswith(f"{key}=") else line
            for line in lines
        )
    else:
        content = content.rstrip("\n") + f"\n{key}={val}\n"

with open(env_path, "w") as f:
    f.write(content)

print(f"\nSaved to .env!")
print("Testing tweet...")

# Test
test_req = Request("https://api.twitter.com/2/tweets", method="POST")
test_req.add_header("Authorization", f"Bearer {access_token}")
test_req.add_header("Content-Type", "application/json")
test_req.data = json.dumps({"text": "iBitLabs Sniper is LIVE - tracking SOL PERP with 3x leverage.\n\nReal money. Real trades. Full transparency.\n\nibitlabs.com"}).encode()

try:
    with urlopen(test_req, timeout=15) as resp:
        result = json.loads(resp.read())
        tid = result.get("data", {}).get("id", "?")
        print(f"Tweet posted! https://x.com/i/status/{tid}")
except Exception as e:
    print(f"Tweet failed: {e}")
