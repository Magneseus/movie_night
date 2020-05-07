from redbot.core import commands
from .movie_bot import MovieNightCog

def setup(bot) -> None:
    bot.add_cog(MovieNightCog(bot))