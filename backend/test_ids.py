import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.core.config import get_settings
from app.services.tmdb import TmdbClient

async def test_tmdb_ids():
    settings = get_settings()
    client = TmdbClient(
        api_key=settings.tmdb_api_key,
        api_base=settings.tmdb_api_base,
        image_base=settings.tmdb_image_base,
        language=settings.default_language,
        proxy=settings.http_proxy,
    )
    
    test_ids = [75865, 72819, 278127, 278043]
    
    for tmdb_id in test_ids:
        print(f"\n==============================")
        print(f"Testing TMDB ID: {tmdb_id}")
        
        # Test as TV
        try:
            tv_details = await client.details("tv", tmdb_id, language_override="zh-CN")
            if tv_details:
                print(f"[TV] Name: {tv_details.get('name')}, Original Name: {tv_details.get('original_name')}")
            else:
                print(f"[TV] Not found")
        except Exception as e:
            pass
            
        # Test as Movie
        try:
            movie_details = await client.details("movie", tmdb_id, language_override="zh-CN")
            if movie_details:
                print(f"[Movie] Title: {movie_details.get('title')}, Original Title: {movie_details.get('original_title')}")
            else:
                print(f"[Movie] Not found")
        except Exception as e:
            pass

    await client.close()

if __name__ == "__main__":
    asyncio.run(test_tmdb_ids())
