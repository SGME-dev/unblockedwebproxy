from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
import re
import base64
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STANDARD_HEADERS = {
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: your_email@example.com) Educational Research Project",
    "Accept-Encoding": "gzip",
}

def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8").replace("=", "")

@app.get("/proxy")
async def proxy_endpoint(request: Request, url: str = Query(..., description="The BASE64 ENCODED target URL")):
    # 1. DECODE THE MAIN TARGET TARGET
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

    # 2. CATCH SUBMITTED FORM PARAMETERS
    # If a form was submitted, its variables will arrive as extra URL arguments (like ?q=godot)
    raw_query_params = request.url.query
    if raw_query_params:
        # Strip away our internal proxy tracking parameter so it doesn't get forwarded to the target website
        clean_params = "&".join([p for p in raw_query_params.split("&") if not p.startswith("url=")])
        if clean_params:
            # Inject the parameters directly into the target destination URL path!
            separator = "&" if "?" in real_url else "?"
            real_url = f"{real_url}{separator}{clean_params}"

    print(f"[PROXY SERVER] Active routed target destination: {real_url}")

    if not real_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid target link protocol.")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(real_url, headers=STANDARD_HEADERS, timeout=10.0)
            content_type = response.headers.get("content-type", "")
            
            if "text/html" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # 3. INTERCEPT ALL FORMS DYNAMICALLY
                # Looks for any form action attribute (e.g., action="/login" or action="https://site.com")
                form_pattern = r'<form\b([^>]*)action=["\']([^"\']+)["\']([^>]*)>'
                
                def replace_form(match):
                    before_action = match.group(1)
                    original_action = match.group(2)
                    after_action = match.group(3)
                    
                    # Convert to full absolute address paths
                    if original_action.startswith("/"):
                        full_action = base_domain + original_action
                    else:
                        full_action = original_action
                    
                    # Encrypt the form action target domain path
                    encrypted_action = encode_url(full_action)
                    
                    # Force the form to submit to our server path, keeping its internal parameters
                    # We inject a hidden target parameter mapping so it catches on next reload pass
                    return f'<form{before_action}action="/proxy" {after_action}><input type="hidden" name="url" value="{encrypted_action}">'

                html_content = re.sub(form_pattern, replace_form, html_content)

                # 4. INTERCEPT HYPERLINKS & ASSETS
                pattern = r'(href|src)=["\'](https?://[^"\']+|/[^"\']+)["\']'
                def replace_link(match):
                    attribute = match.group(1)
                    original_link = match.group(2)
                    
                    if original_link.startswith("/"):
                        full_link = base_domain + original_link
                    else:
                        full_link = original_link
                    
                    encrypted_link = encode_url(full_link)
                    return f'{attribute}="/proxy?url={encrypted_link}"'

                modified_html = re.sub(pattern, replace_link, html_content)
                return Response(content=modified_html, media_type="text/html")
            
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
