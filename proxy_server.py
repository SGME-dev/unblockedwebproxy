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

MASTER_HEADERS = {
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: ezragoswami@gmail.com) Educational Research Project",
    "Accept-Encoding": "gzip",
    "Accept": "*/*",
}

def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8").replace("=", "")

@app.get("/proxy")
async def proxy_endpoint(request: Request, url: str = Query(..., description="The BASE64 ENCODED target URL")):
    # 1. DYNAMICALLY DETECT YOUR ACTIVE RENDER DOMAIN
    # This ensures your rewritten links always target your app directly rather than the proxy host!
    host_header = request.headers.get("host", "://onrender.com")
    scheme = request.url.scheme
    my_base_proxy_url = f"{scheme}://{host_header}"

    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

    # 📺 FIXED YOUTUBE VIDEO CONVERSION BLOCK
    if "://youtube.com" in real_url or "youtu.be/" in real_url:
        try:
            video_id = ""
            if "watch?v=" in real_url:
                video_id = real_url.split("watch?v=")[1].split("&")[0]
            elif "youtu.be/" in real_url:
                video_id = real_url.split("youtu.be/")[1].split("?")[0]
            
            if video_id:
                real_url = f"https://youtube.com{video_id}"
                print(f"[VIDEO ENGINE] Successfully converted link to embed layout: {real_url}")
        except Exception as e:
            print(f"[VIDEO ENGINE ERROR] Slicing text layout hit an error: {e}")

    print(f"[PROXY ENGINE] Contacting destination: {real_url}")

    if not real_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid target link protocol.")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(real_url, headers=MASTER_HEADERS, timeout=15.0)
            content_type = response.headers.get("content-type", "")
            
            if "text/html" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # Intercept hyperlinks and source assets cleanly
                pattern = r'(href|src)=["\'](https?://[^"\']+|/[^"\']+)["\']'
                
                def replace_link(match):
                    attribute = match.group(1)
                    original_link = match.group(2)
                    
                    if original_link.startswith("/"):
                        full_link = base_domain + original_link
                    else:
                        full_link = original_link
                        
                    encrypted_link = encode_url(full_link)
                    
                    # 🛠️ THE CRITICAL BUG FIX: Always prefix the link with your absolute cloud URL path
                    return f'{attribute}="{my_base_proxy_url}/proxy?url={encrypted_link}"'

                modified_content = re.sub(pattern, replace_link, html_content)
                return Response(content=modified_content, media_type=content_type)
            
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
