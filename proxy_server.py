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

@app.get("/search_proxy")
async def search_proxy_endpoint(request: Request):
    """
    Safely captures browser search bar inputs, tracks the parent site domain,
    and automatically bundles them into an encrypted Base64 loopback redirect.
    """
    raw_query_string = request.url.query
    referer_header = request.headers.get("referer", "")
    
    # Default fallback website
    base_site = "https://yewtu.be" 
    
    print(f"[SEARCH DEBUG] Raw incoming search query parameters: {raw_query_string}")
    print(f"[SEARCH DEBUG] Incoming referer history header path: {referer_header}")
    
    if "url=" in referer_header:
        try:
            # Cleanly isolate the active Base64 hash parameter from the tracking string
            parts = referer_header.split("url=")
            if len(parts) > 1:
                hash_part = parts[1].split("&")[0]
                # Re-apply correct string bit padding so Base64 doesn't throw a parsing error
                padded_hash = hash_part + "=" * ((4 - len(hash_part) % 4) % 4)
                decoded_parent = base64.urlsafe_b64decode(padded_hash).decode("utf-8")
                
                # Extract the pure base website domain string
                domain_match = re.match(r"(https?://[^/]+)", decoded_parent)
                if domain_match:
                    base_site = domain_match.group(1)
                    print(f"[SEARCH DEBUG] Successfully traced parent context domain: {base_site}")
        except Exception as e:
            print(f"[SEARCH ERROR] Internal tracking algorithm failed: {e}")

    # Build the target redirect URL
    if not raw_query_string:
        target_search_url = base_site
    else:
        target_search_url = f"{base_site}/search?{raw_query_string}"
    
    print(f"[SEARCH SUCCESS] Assembled absolute search target: {target_search_url}")

    # Convert the full path to a safe hash string
    encrypted_target = encode_url(target_search_url)
    
    # Issue a clean status 307 temporary redirect to pass back to the main loop function
    return Response(
        status_code=307, 
        headers={"Location": f"/proxy?url={encrypted_target}"}
    )

@app.get("/proxy")
async def proxy_endpoint(url: str = Query(..., description="The BASE64 ENCODED target URL")):
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
        print(f"[PROXY SERVER] Fetching destination: {real_url}")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

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

                # 1. INTERCEPT FORMS (Fixes search inputs)
                form_pattern = r'action=["\'](/[^"\']+|https?://[^"\']+)["\']'
                html_content = re.sub(form_pattern, 'action="/search_proxy"', html_content)

                # 2. INTERCEPT HYPERLINKS & IMAGES
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
