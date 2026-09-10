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

MASTER_HEADERS = {
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: ezragoswami@gmail.com) Educational Research Project",
    "Accept-Encoding": "gzip",
    "Accept": "*/*",
}

MY_APP_DOMAIN = "https://unblocked-web-proxy.onrender.com"

def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8").replace("=", "")

# 🚀 THE MASTER GLOBAL ROUTING INTERCEPTOR
class GlobalProxyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if path in ["/proxy", "/docs", "/openapi.json"] or path.startswith("/static"):
            return await call_next(request)
            
        referer = request.headers.get("referer", "")
        
        if "url=" in referer:
            try:
                # Isolate the Base64 hash parameter from history context safely
                hash_part = referer.split("url=")[1].split("&")[0]
                padded_hash = hash_part + "=" * ((4 - len(hash_part) % 4) % 4)
                decoded_parent = base64.urlsafe_b64decode(padded_hash).decode("utf-8")
                
                domain_match = re.match(r"(https?://[^/]+)", decoded_parent)
                if domain_match:
                    base_site = domain_match.group(1)
                    
                    if not path.startswith("/"):
                        path = "/" + path
                        
                    full_target_url = f"{base_site}{path}"
                    raw_query = request.url.query
                    if raw_query:
                        full_target_url += f"?{raw_query}"
                        
                    print(f"[MIDDLEWARE CATCH] Fixing relative asset to target: {full_target_url}")
                    
                    encrypted_target = encode_url(full_target_url)
                    return Response(
                        status_code=307,
                        headers={"Location": f"{MY_APP_DOMAIN}/proxy?url={encrypted_target}"}
                    )
            except Exception as e:
                print(f"[MIDDLEWARE ERROR] Global routing adjustment failed: {e}")
                
        return await call_next(request)

app.add_middleware(GlobalProxyMiddleware)

@app.api_route("/proxy", methods=["GET", "POST"])
async def proxy_endpoint(request: Request, url: str = Query(..., description="The BASE64 ENCODED target URL")):
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

    # 📺 MASTER REGEX SUB OVERRIDE (Fixes the missing slash and domain fusion bug permanently)
    if "youtube.com" in real_url or "youtu.be" in real_url:
        try:
            # 1. Catch standard desktop links: https://youtube.com -> https://youtube.com
            if "watch?v=" in real_url:
                real_url = re.sub(r"https?://(www\.)?youtube\.com/watch\?v=([^&#]+).*", r"https://youtube.com\2", real_url)
            
            # 2. Catch mobile share links: https://youtu.be -> https://youtube.com
            elif "youtu.be/" in real_url:
                real_url = re.sub(r"https?://youtu\.be/([^?&#]+).*", r"https://youtube.com\1", real_url)
                
            print(f"[VIDEO ENGINE] Successfully rebuilt URL destination: {real_url}")
        except Exception as e:
            print(f"[VIDEO ENGINE ERROR] Sub match routing failed: {e}")

    print(f"[PROXY ENGINE] Fetching target: {real_url}")

    if not real_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid target link protocol.")

    method = request.method
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            req_data = await request.body() if method == "POST" else None
            response = await client.request(
                method, real_url, headers=MASTER_HEADERS, content=req_data, timeout=15.0
            )
            content_type = response.headers.get("content-type", "")
            
            if "text/html" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                pattern = r'(href|src)=["\'](https?://[^"\']+|/[^"\']+)["\']'
                
                def replace_link(match):
                    attribute = match.group(1)
                    original_link = match.group(2)
                    
                    if original_link.startswith("/"):
                        full_link = base_domain + original_link
                    else:
                        full_link = original_link
                        
                    encrypted_link = encode_url(full_link)
                    return f'{attribute}="{MY_APP_DOMAIN}/proxy?url={encrypted_link}"'

                modified_content = re.sub(pattern, replace_link, html_content)
                return Response(content=modified_content, media_type=content_type)
            
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
