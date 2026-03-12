import asyncio
import httpx


async def test_httpx():
    url = "https://www.google.com/search?hl=en&num=15&q=Amco+Ranger+Termite+&+Pest+Solutions+executive+team+site:crunchbase.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Not=A?Brand";v="8", "Chromium";v="131"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, follow_redirects=True)
        print(f"Status: {response.status_code}")
        print(f"Content length: {len(response.text)}")
        if "sorry/index" in response.text or response.status_code == 429:
            print("BLOCKED: Google Sorry page detected.")
        else:
            print("SUCCESS: Google search returned organic page.")


if __name__ == "__main__":
    asyncio.run(test_httpx())
