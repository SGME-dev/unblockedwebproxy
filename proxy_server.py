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

# Unified standard tracking headers for all websites (including Wikipedia and YouTube)
MASTER_HEADERS = {
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: ezragoswami@gmail.com) Educational Research Project",
    "Accept-Encoding": "gzip",
    "Accept": "*/*",
}

def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8").replace("=", "")

# 🚀 THE MASTER GLOBAL ROUTING INTERCEPTOR (Catches relative browser requests)
class GlobalProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if path in ["/proxy", "/docs", "/openapi.json"] or path.startswith("/static"):
            return await call_next(request)
            
        referer = request.headers.get("referer", "")
        
        if "url=" in referer:
            try:
                # Isolate the Base64 hash parameter from your history context
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
                        
                    print(f"[MIDDLEWARE REDIRECT] Fixing relative route: {full_target_url}")
                    
                    encrypted_target = encode_url(full_target_url)
                    return Response(
                        status_code=307,
                        headers={"Location": f"/proxy?url={encrypted_target}"}
                    )
            except Exception as e:
                print(f"[MIDDLEWARE ERROR] Global routing adjustment failed: {e}")
                
        return await call_next(request)

app.add_middleware(GlobalProxyMiddleware)

# 🛠️ JAVASCRIPT INJECTION PAYLOAD
JS_INJECTION = """
<script>
(function() {
    console.log("[PROXY CLIENT] Intercepting background script requests...");

    function encodeUrl(url) {
        try {
            var absoluteUrl = new URL(url, window.location.href).href;
            var b64 = btoa(unescape(encodeURIComponent(absoluteUrl)));
            return b64.replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=/g, '');
        } catch(e) { return url; }
    }

    // Intercept JavaScript fetch() APIs
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        let resource = args[0];
        if (typeof resource === 'string' && !resource.includes('/proxy') && !resource.startsWith('data:')) {
            args[0] = '/proxy?url=' + encodeUrl(resource);
        }
        return originalFetch.apply(this, args);
    };

    // Intercept JavaScript XMLHttpRequest APIs
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...args) {
        if (typeof url === 'string' && !url.includes('/proxy') && !url.startsWith('data:')) {
            url = '/proxy?url=' + encodeUrl(url);
        }
        return originalOpen.apply(this, [method, url, ...args]);
    };
})();
</script>
"""

@app.get("/proxy")
async def proxy_endpoint(request: Request, url: str = Query(..., description="The BASE64 ENCODED target URL")):
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

    # 🔄 ADDED YOUTUBE VIDEO LINK REDIRECTION FILTER
    # Automatically forces regular watch pages into Google's lightweight embed system
    if "://youtube.com" in real_url or "youtu.be/" in real_url:
        video_id = ""
        if "watch?v=" in real_url:
            video_id = real_url.split("watch?v=")[1].split("&")[0]
        elif "youtu.be/" in real_url:
            video_id = real_url.split("youtu.be/")[1].split("?")[0]
            
        if video_id:
            real_url = f"https://youtube.com{video_id}"
            print(f"[VIDEO ENGINE] Auto-forwarded video link to Embed Player: {real_url}")

    print(f"[PROXY ENGINE] Fetching target: {real_url}")

    if not real_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid target link protocol.")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            # All sites now pass through our unified master tracking bot header format
            response = await client.get(real_url, headers=MASTER_HEADERS, timeout=15.0)
            content_type = response.headers.get("content-type", "")
            
            if "text/html" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # Inject our custom JS script right inside the page header
                html_content = re.sub(r"<head>", f"<head>{JS_INJECTION}", html_content, flags=re.IGNORECASE)

                # 🔄 LINK REWRITING ENGINE: Transforms standard href/src links into web proxy format
                pattern = r'(href|src)=["\'](https?://[^"\']+|/[^"\']+)["\']'
                
                def replace_link(match):
                    attribute = match.group(1) # 'href' or 'src'
                    original_link = match.group(2)
                    
                    # Convert internal relative links (like /wiki/Science) into absolute paths
                    if original_link.startswith("/"):
                        full_link = base_domain + original_link
                    else:
                        full_link = original_link
                        
                    # Turn the complete web path link into our encrypted proxy parameter layout
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
