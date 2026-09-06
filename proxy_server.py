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

STANDARD_HEADERS = {
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: your_email@example.com) Educational Research Project",
    "Accept-Encoding": "gzip",
}

def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8").replace("=", "")

# 🚀 THE MASTER GLOBAL ROUTING INTERCEPTOR
class GlobalProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # If the browser successfully routes to our active endpoints, let it pass normally
        if path in ["/proxy", "/docs", "/openapi.json"] or path.startswith("/static"):
            return await call_next(request)
            
        # 🕵️ CATCH ALL UNHANDLED ROUTE TRAFFIC (Like YouTube's /results)
        referer = request.headers.get("referer", "")
        
        if "url=" in referer:
            try:
                # Isolate the Base64 hash parameter from your history context
                hash_part = referer.split("url=")[1].split("&")[0]
                padded_hash = hash_part + "=" * ((4 - len(hash_part) % 4) % 4)
                decoded_parent = base64.urlsafe_b64decode(padded_hash).decode("utf-8")
                
                # Extract the base target root server domain (e.g., https://www.youtube.com)
                domain_match = re.match(r"(https?://[^/]+)", decoded_parent)
                if domain_match:
                    base_site = domain_match.group(1)
                    
                    # Reconstruct the absolute target destination YouTube path
                    raw_query = request.url.query
                    full_target_url = f"{base_site}{path}"
                    if raw_query:
                        full_target_url += f"?{raw_query}"
                        
                    print(f"[MIDDLEWARE REDIRECT] Intercepted raw request! Fixing path to: {full_target_url}")
                    
                    # Encrypt the compiled destination string layout into a safe proxy URL
                    encrypted_target = encode_url(full_target_url)
                    
                    # Issue a clear Temporary Redirect (Status 307) to keep parameters safe
                    return Response(
                        status_code=307,
                        headers={"Location": f"/proxy?url={encrypted_target}"}
                    )
            except Exception as e:
                print(f"[MIDDLEWARE ERROR] Global routing adjustment pass failed: {e}")
                
        return await call_next(request)

# Register our global interceptor middleware
app.add_middleware(GlobalProxyMiddleware)

@app.get("/proxy")
async def proxy_endpoint(request: Request, url: str = Query(..., description="The BASE64 ENCODED target URL")):
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

    print(f"[PROXY ENGINE] Fetching active stream target: {real_url}")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            # Mirror any background API arguments sent directly by web player components
            response = await client.get(real_url, headers=STANDARD_HEADERS, timeout=15.0)
            content_type = response.headers.get("content-type", "")
            
            # Rewrite paths on text-based web layouts
            if "text/html" in content_type or "application/javascript" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # Intercept links and resource elements dynamically
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
            
            # Pipe images, media, or data streams directly back
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
