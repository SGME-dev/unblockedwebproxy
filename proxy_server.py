from fastapi import FastAPI, HTTPException, Query, Response
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
    "User-Agent": "EducationalSchoolProxyBot/1.0 (contact: ezragoswami@gmail.com) Educational Research Project",
    "Accept-Encoding": "gzip",  
}


# Helper function to encode URLs to Base64 (so links match our system format)
def encode_url(url: str) -> str:
    url_bytes = url.encode("utf-8")
    base64_bytes = base64.urlsafe_b64encode(url_bytes)
    return base64_bytes.decode("utf-8")

@app.get("/proxy")
async def proxy_endpoint(url: str = Query(..., description="The BASE64 ENCODED target URL")):
    # 1. DECODE THE URL
    try:
        padded_url = url + "=" * ((4 - len(url) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded_url)
        real_url = decoded_bytes.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to decode hash.")

    if not real_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid target link protocol.")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(real_url, headers=STANDARD_HEADERS, timeout=10.0)
            content_type = response.headers.get("content-type", "")
            
            # 2. THE REWRITER ENGINE FOR WEBPAGES
            if "text/html" in content_type:
                html_content = response.text
                
                # Determine the base domain to resolve relative paths (e.g., https://example.com)
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # Regex pattern to find all standard href and src links
                # Matches patterns like href="https://site.com" or src="/image.png"
                pattern = r'(href|src)=["\'](https?://[^"\']+|/[^"\']+)["\']'

                def replace_link(match):
                    attribute = match.group(1)  # 'href' or 'src'
                    original_link = match.group(2)
                    
                    # Convert relative links (like /style.css) into full absolute links
                    if original_link.startswith("/"):
                        full_link = base_domain + original_link
                    else:
                        full_link = original_link
                    
                    # Encrypt the link using our client routine format
                    encrypted_link = encode_url(full_link)
                    
                    # Return the rewritten attribute pointing directly back to our server
                    # Render will dynamically fill in the correct domain hosting your app
                    return f'{attribute}="/proxy?url={encrypted_link}"'

                # Execute the comprehensive page rewrite pass
                modified_html = re.sub(pattern, replace_link, html_content)
                return Response(content=modified_html, media_type="text/html")
            
            # 3. For images/videos/scripts, pass them back directly
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
