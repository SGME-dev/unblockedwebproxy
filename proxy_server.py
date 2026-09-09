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

# Clean, unified headers following automated API rules
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
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode hash structure.")

    # 📺 FIXING THE YOUTUBE VIDEO PROBLEM (Safe Extraction Loop)
    if "://youtube.com" in real_url or "youtu.be/" in real_url:
        try:
            video_id = ""
            if "watch?v=" in real_url:
                # Isolate the text piece after watch?v=
                video_id = real_url.split("watch?v=")[1].split("&")[0]
            elif "youtu.be/" in real_url:
                # Isolate the mobile ID piece
                video_id = real_url.split("youtu.be/")[1].split("?")[0]
            
            if video_id:
                # Force the proxy to fetch Google's embed fullscreen video layout
                real_url = f"https://youtube.com{video_id}"
                print(f"[VIDEO ENGINE] Success! Swapped link to embed: {real_url}")
        except Exception as e:
            print(f"[VIDEO ENGINE ERROR] Slicing string hit a snag: {e}")

    # Log statement so you can see exactly what your server is connecting to
    print(f"[PROXY ENGINE] Fetching clean target: {real_url}")

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

                # Core regex parsing system that successfully maps page links
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
