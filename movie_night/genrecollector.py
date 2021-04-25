import aiohttp
import asyncio

# Grab the movie genre in a slightly painful way
async def get_genre(movie_title, session):
    search_string = "+".join(movie_title.split())
    url = f'https://www.google.com/search?q={search_string}'
    async with session.get(url) as resp:
        html = await resp.text()
        # this represents the dot symbol that appears on either
        # side of the genre on a google knowledge panel.
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
        
        
        
        
        
        
        
        
        
        
        
            
            
            
            
            
            