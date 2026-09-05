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
            
            # UPDATE THE HTML PARSING PASS IN YOUR proxy_server.py:

            if "text/html" in content_type:
                html_content = response.text
                
                domain_match = re.match(r"(https?://[^/]+)", real_url)
                base_domain = domain_match.group(1) if domain_match else real_url

                # 1. REWRITE FORMS: Intercept any <form action="..."> lines
                # This catches the search bars and sends them back to our /search_proxy endpoint
                form_pattern = r'action=["\'](/[^"\']+|https?://[^"\']+)["\']'
                
                def replace_form(match):
                    original_action = match.group(1)
                    if original_action.startswith("/"):
                        full_action = base_domain + original_action
                    else:
                        full_action = original_action
                    
                    # We pass the base domain inside a hidden helper parameter so the server knows where to search
                    return f'action="/search_proxy?base_site={base_domain}"'

                html_content = re.sub(form_pattern, replace_form, html_content)

                # 2. STANDARD LINKS (Our existing link rewriter logic continues below)
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

            
            # 3. For images/videos/scripts, pass them back directly
            return Response(content=response.content, media_type=content_type)
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Target unreachable: {exc}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

@app.get("/search_proxy")
async def search_proxy_endpoint(
    base_site: str = Query(..., description="The base website domain"),
    q: str = Query(None, description="The search query text parameter")
):
    """
    Catches raw browser search bar inputs, formats them into a clean absolute link,
    encrypts them to Base64, and redirects safely back into our main proxy routine loop.
    """
    if not q:
        # If the search field was blank, just drop back to the main homepage
        target_search_url = base_site
    else:
        # Standard query assembly (e.g., https://yewtu.be)
        target_search_url = f"{base_site}/search?q={q.replace(' ', '+')}"
    
    # Encrypt the compiled destination string into our Base64 string format
    encrypted_target = encode_url(target_search_url)
    
    # Issue an automated redirect response back to our main /proxy layout route
    return Response(
        status_code=307, 
        headers={"Location": f"/proxy?url={encrypted_target}"}
    )

