from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import re
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@app.get("/proxy")
async def proxy_endpoint(url: str = Query(..., description="The BASE64 ENCODED target URL")):
    # 1. DECODE THE URL FROM THE CLIENT
    try:
        # Pad the string with '=' if it's missing trailing padding characters
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
        print(f"[SERVER] Decrypted request destination: {real_url}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode URL hash: {e}")

    if not real_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid decrypted protocol. Must be HTTP or HTTPS.")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(real_url, headers=STANDARD_HEADERS, timeout=10.0)
            content_type = response.headers.get("content-type", "")
            
            # 2. IF HTML, INJECT BASE TAG (We will make this tag look for base64 links next)
            if "text/html" in content_type:
                html_content = response.text
                proxy_base_url = f"http://localhost:8000/proxy?url={url}/../"
                
                modified_html = re.sub(
                    r"<head>",
                    f"<head><base href='{proxy_base_url}'>",
                    html_content,
                    flags=re.IGNORECASE
                )
                return Response(content=modified_html, media_type="text/html")
            
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Error contacting target site: {exc}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
