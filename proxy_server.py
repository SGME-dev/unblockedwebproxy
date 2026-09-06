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

# 🕵️ DYNAMIC HEADER SELECTIONS
# Wikipedia demands an honest bot name + contact email
WIKIPEDIA_HEADERS = {
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: ezragoswami@gmail.com) Educational Research Project",
    "Accept-Encoding": "gzip",
}

# YouTube demands mobile Apple headers to bypass heavy scraping firewalls
YOUTUBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
    "X-YouTube-Client-Name": "5",  
    "X-YouTube-Client-Version": "17.07.2",
}

# Fallback headers for standard websites (like Minecraft.net)
GENERIC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8").replace("=", "")

# 🚀 THE MASTER GLOBAL ROUTING INTERCEPTOR (Catches relative scripts/form actions)
class GlobalProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Allow native routing targets to skip interception logic loops
        if path in ["/proxy", "/docs", "/openapi.json"] or path.startswith("/static"):
            return await call_next(request)
            
        # Catch unexpected route configurations (like YouTube's /results)
        referer = request.headers.get("referer", "")
        
        if "url=" in referer:
            try:
                # Safely slice and isolate the active Base64 link data hash block
                hash_part = referer.split("url=")[1].split("&")[0]
                padded_hash = hash_part + "=" * ((4 - len(hash_part) % 4) % 4)
                decoded_parent = base64.urlsafe_b64decode(padded_hash).decode("utf-8")
                
                # Reconstruct the absolute target destination address domain path
                domain_match = re.match(r"(https?://[^/]+)", decoded_parent)
                if domain_match:
                    base_site = domain_match.group(1)
                    
                    raw_query = request.url.query
                    full_target_url = f"{base_site}{path}"
                    if raw_query:
                        full_target_url += f"?{raw_query}"
                        
                    print(f"[MIDDLEWARE REDIRECT] Fixing relative route to absolute: {full_target_url}")
                    
                    # Wrap and return a safe Base64 loopback redirection
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

    # Apply smart heading conditions based on what website name is inside the string link
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
            
            # Rewrite paths on matching code content blocks
            if "text/html" in content_type or "application/javascript" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # Intercept links, media locations, and static script modules
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
            
            # Pipe straight images or raw audio/video buffers back to browser view frames
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

