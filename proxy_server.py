from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
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

WIKIPEDIA_HEADERS = {
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: ezragoswami@gmail.com) Educational Research Project",
    "Accept-Encoding": "gzip",
}

YOUTUBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
    "X-YouTube-Client-Name": "5",  
    "X-YouTube-Client-Version": "17.07.2",
}

GENERIC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8").replace("=", "")

# 🛠️ JAVASCRIPT INJECTION PAYLOAD
# This script injects directly into the iPad browser. It intercepts JavaScript fetch requests 
# and automatically wraps them in our Base64 proxy configuration before the network triggers.
JS_INJECTION = """
<script>
(function() {
    console.log("[PROXY CLIENT] Initialising network interception hooks...");

    // Helper function to convert text strings to Base64 in JavaScript
    function encodeUrl(url) {
        try {
            var absoluteUrl = new URL(url, window.location.href).href;
            var b64 = btoa(unescape(encodeURIComponent(absoluteUrl)));
            return b64.replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=/g, '');
        } catch(e) { return url; }
    }

    # 1. INTERCEPT FETCH() REQUESTS
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        let resource = args[0];
        let config = args[1] || {};
        
        if (typeof resource === 'string' && !resource.includes('/proxy')) {
            let proxyTarget = encodeUrl(resource);
            resource = '/proxy?url=' + proxyTarget;
        }
        args[0] = resource;
        return originalFetch.apply(this, args);
    };

    # 2. INTERCEPT XHR (XMLHttpRequest) REQUESTS
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...args) {
        if (typeof url === 'string' && !url.includes('/proxy')) {
            url = '/proxy?url=' + encodeUrl(url);
        }
        return originalOpen.apply(this, [method, url, ...args]);
    };
})();
</script>
"""

class GlobalProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in ["/proxy", "/docs", "/openapi.json"] or path.startswith("/static"):
            return await call_next(request)
            
        referer = request.headers.get("referer", "")
        if "url=" in referer:
            try:
                hash_part = referer.split("url=")[1].split("&")[0]
                padded_hash = hash_part + "=" * ((4 - len(hash_part) % 4) % 4)
                decoded_parent = base64.urlsafe_b64decode(padded_hash).decode("utf-8")
                
                domain_match = re.match(r"(https?://[^/]+)", decoded_parent)
                if domain_match:
                    base_site = domain_match.group(1)
                    raw_query = request.url.query
                    full_target_url = f"{base_site}{path}"
                    if raw_query:
                        full_target_url += f"?{raw_query}"
                        
                    print(f"[MIDDLEWARE REDIRECT] Fixing relative route to absolute: {full_target_url}")
                    encrypted_target = encode_url(full_target_url)
                    return Response(
                        status_code=307,
                        headers={"Location": f"/proxy?url={encrypted_target}"}
                    )
            except Exception as e:
                print(f"[MIDDLEWARE ERROR] Global routing loop calculations crashed: {e}")
                
        return await call_next(request)

app.add_middleware(GlobalProxyMiddleware)

@app.get("/proxy")
async def proxy_endpoint(request: Request, url: str = Query(..., description="The BASE64 ENCODED target URL")):
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

    active_headers = GENERIC_HEADERS
    if "wikipedia.org" in real_url:
        active_headers = WIKIPEDIA_HEADERS
        print(f"[PROXY ENGINE] Applying verified Wikipedia bot profile to fetch: {real_url}")
    elif "youtube.com" in real_url or "youtu.be" in real_url:
        active_headers = YOUTUBE_HEADERS
        print(f"[PROXY ENGINE] Applying iOS streaming spoof profile to fetch: {real_url}")
    else:
        print(f"[PROXY ENGINE] Fetching standard domain target: {real_url}")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(real_url, headers=active_headers, timeout=15.0)
            content_type = response.headers.get("content-type", "")
            
            if "text/html" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # Inject our JavaScript network hooks right after the HTML <head> element opens
                html_content = re.sub(r"<head>", f"<head>{JS_INJECTION}", html_content, flags=re.IGNORECASE)

                # Intercept normal HTML links and asset locations
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

                modified_content = re.sub(pattern, replace_link, html_content)
                return Response(content=modified_content, media_type=content_type)
            
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
