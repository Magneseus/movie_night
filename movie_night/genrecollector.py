import urllib
import aiohttp
import time
import asyncio

async def get_genre(movie_title, session):
    search_string = "+".join(movie_title.split())
    url = f'https://www.google.com/search?q={search_string}'
    print(url)
    async with session.get(url) as resp:
        html = await resp.text()
        parts = html.split("&#8231;")
        if len(parts) < 3:
            return "Unknown"
        
        return parts[1].strip()
            
async def get_genres(movie_list):
    REQ_HDRS = {
        'User-Agent': 'python-requests/2.25.1',
        'Accept-Encoding': 'gzip, deflate',
        'Accept': '*/*',
        'Connection': 'keep-alive'
    }
    tasks = []
    async with aiohttp.ClientSession(headers=REQ_HDRS) as session:
        for movie in movie_list:
            tasks.append(get_genre(movie, session))
        
        genres = await asyncio.gather(*tasks)
        return genres
        
        
        
        
        
        
        
        
        
        
        
            
            
            
            
            
            