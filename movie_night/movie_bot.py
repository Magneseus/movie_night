import discord
from redbot.core import commands
from redbot.core import Config
from redbot.core import checks

import pytz
from datetime import datetime
from croniter import croniter

from .voteinfo import VoteInfo, VoteException

class MovieNightCog(commands.Cog):
    """Custom Movie Night Cog"""
    
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.bot = bot
        
        # 77 79 86 73 69 == 'MOVIE'
        self.config = Config.get_conf(self, identifier=7779867369)
        
        default_global = {}
        
        default_guild = {
            "vote_size": 10,
            "suggestions": [],
            "timezone_str": "UTC",
            "movie_time": "0 20 * * 5"
        }
        
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        
        self.vote_info = {}
        
    
    """Helper Functions"""
    async def get_vote_info(self, ctx: commands.Context) -> VoteInfo:
        if ctx.guild.id not in self.vote_info:
            self.vote_info[ctx.guild.id] = VoteInfo()
        
        return self.vote_info[ctx.guild.id]
    
    
    """Global Commands"""
    
    @commands.command(name="suggest")
    async def _cmd_add_suggestion(self, ctx: commands.Context, movie_title:str, *args):
        """Adds a movie suggestion to the list of possible movies to watch."""
        full_movie_title = movie_title + " " + " ".join(args)
        
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            if full_movie_title in suggestions:
                await ctx.send(f"\"**{full_movie_title}**\" is already in the list!")
            else:
                suggestions.append(full_movie_title)
                await ctx.send(f"\"**{full_movie_title}**\" has been added to the list of movie suggestions.")
    
    @commands.command(name="unsuggest")
    async def _cmd_del_suggestion(self, ctx: commands.Context, movie_index:int):
        """Removes a movie suggestion from the list of possible movies to watch. eg. [p]unsuggest 1"""
        movie_index = movie_index - 1
        
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            if movie_index < 0 or movie_index >= len(suggestions):
                await ctx.send(f"That isn't a valid index, sorry! Please check the current list with: `{ctx.prefix}suggestions`.")
            else:
                movie_name = suggestions.pop(movie_index)
                await ctx.send(f"\"**{movie_name}**\" has been removed from the list of movie suggestions.")
    
    @commands.command(name="vote")
    async def _cmd_vote(self, ctx: commands.Context, vote:str, *args):
        """
        Votes for one or more movies in the current vote. eg. [p]vote a | [p]vote a,d,e
        (Hint: You can also use the reacts down below to vote!)
        """
        full_vote = vote + " " + " ".join(args)
        vinfo = await self.get_vote_info(ctx)
        
        try:
            await vinfo.add_user_vote(full_vote, ctx.message.author.id)
        except VoteException as ve:
            await ctx.send(str(ve))
        else:
            await ctx.send("Vote submitted!")
    
    @commands.command(name="suggestions")
    async def _cmd_list_suggestions(self, ctx: commands.Context):
        """Lists all current movie suggestions."""
        suggestions = await self.config.guild(ctx.guild).suggestions()
        
        #suggestions_list = list(map(lambda x: f"{x[0]}) {x[1]}\n", zip(range(1, len(suggestions)+1), suggestions)))
        suggestions_list = [f"{ind}) {suggestions[ind-1]}\n" for ind in range(1, len(suggestions)+1)]
        
        suggestions_str = "".join(suggestions_list)
        
        em = discord.Embed(
            title="**Movie Suggestions:**\n",
            description=suggestions_str,
            color=discord.Color.green()
        )
        
        await ctx.send(embed=em)
    
    @commands.command(name="next_movie")
    async def _cmd_next_movie(self, ctx: commands.Context):
        """Prints the name and date of the next Movie Night."""
        # TODO
        pass
    
    """Admin Commands"""
    
    @commands.group(name="mn", autohelp=False)
    @checks.mod()
    async def _cmd_movie_night(self, ctx: commands.Context):
        """Movie Night Admin Commands"""
        if ctx.invoked_subcommand is None:
            prefix = ctx.prefix
            
            title = "**Welcome to Movie Nights.**\n"
            description = """\n
            **Commands**\n
            ``{0}mn reorder``: Re-orders the list of movie suggestions.\n
            ``{0}mn clear_suggestions``: Clears the list of movie suggestions.\n
            ``{0}mn start_vote``: Starts a vote for the next movie to watch.\n
            ``{0}mn stop_vote``: Stops the on-going vote for the next movie to watch.\n
            ``{0}mn cancel_vote``: Cancels the on-going vote.\n
            ``{0}mn size``: Changes the maximum number of options for votes.\n
            ``{0}mn timezone``: Sets the timezone for the server.\n
            ``{0}mn reminder``: Sets a reoccurring reminder for Movie Nights!\n
            \n"""
            
            em = discord.Embed(
                title=title,
                description=description.format(prefix),
                color=discord.Color.green()
            )
            
            await ctx.send(embed=em)
    
    @_cmd_movie_night.command(name="reorder")
    async def _cmd_reorder_suggestions(self, ctx: commands.Context, new_order:str):
        """Re-orders the suggestions, relevant when a max. # of options is set for voting."""
        try:
            order_list = list(map(lambda x: int(x) - 1, new_order.split(",")))
        except ValueError:
            await ctx.send("Format must be comma-separated numbers!")
            return
        
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            verify = list(set(order_list))
            verify_len = len(verify)
            
            if verify_len != len(order_list):
                await ctx.send("Cannot contain duplicate indices!")
                return
            
            verify.sort()
            start_ind = verify[0]
            end_ind = verify[-1]
            
            if verify_len == 0 or verify_len > len(suggestions) or verify[0] < 0 or verify[-1] >= len(suggestions) or (verify[-1] - verify[0] + 1) != verify_len:
                await ctx.send("Re-ordered list must be a non-empty subset of the *ordered* suggestions list, and contain all values between the subset's least and greatest elements.")
                return
            
            new_suggestions = suggestions[0:start_ind]
            for ind in order_list:
                new_suggestions.append(suggestions[ind])
            new_suggestions += suggestions[end_ind+1:]
            
            suggestions.clear()
            suggestions += new_suggestions
            
            await ctx.send(f"Suggestions have been re-ordered!")
            await self._cmd_list_suggestions(ctx)
    
    @_cmd_movie_night.command(name="clear_suggestions")
    async def _cmd_clear_suggestions(self, ctx: commands.Context):
        """Clears the suggestions list."""
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            suggestions.clear()
            await ctx.send("Suggestions list has been cleared!")
    
    @_cmd_movie_night.command(name="size")
    async def _cmd_size_vote(self, ctx: commands.Context, num_options:int = 10):
        """Sets the maximum number of options when creating a vote."""
        vinfo = await self.get_vote_info(ctx)
        
        if vinfo.is_voting_enabled():
            await ctx.send("Cannot change the size of a vote while voting is occurring!")
        elif num_options <= 0 or num_options > 26:
            await ctx.send("Cannot change the size of a vote to a number <= 0 or > 26!")
        else:
            await self.config.guild(ctx.guild).vote_size.set(num_options)
            await ctx.send(f"Maximum number of choices for a vote is now set to: `{num_options}`")
    
    @_cmd_movie_night.command(name="start_vote")
    async def _cmd_start_vote(self, ctx: commands.Context):
        """Starts a vote for choosing the next movie."""
        vinfo = await self.get_vote_info(ctx)
        
        suggestions = await self.config.guild(ctx.guild).suggestions()
        vote_size = await self.config.guild(ctx.guild).vote_size()
        
        try:
            await vinfo.start_vote(suggestions[:vote_size], ctx)
        except VoteException as ve:
            await ctx.send(str(ve))
    
    @_cmd_movie_night.command(name="stop_vote")
    async def _cmd_stop_vote(self, ctx: commands.Context):
        """Stops the ongoing vote for the next movie (if any)."""
        vinfo = await self.get_vote_info(ctx)
        try:
            await vinfo.stop_vote(ctx)
        except VoteException as ve:
            await ctx.send(str(ve))
    
    @_cmd_movie_night.command(name="cancel_vote")
    async def _cmd_cancel_vote(self, ctx: commands.Context):
        """Stops the ongoing vote for the next movie (if any)."""
        vinfo = await self.get_vote_info(ctx)
        try:
            await vinfo.cancel_vote()
        except VoteException as ve:
            await ctx.send(str(ve))
    
    @_cmd_movie_night.command(name="timezone")
    async def _cmd_set_timezone(self, ctx: commands.Context, new_timezone_str):
        """Sets the timezone for a specific guild."""
        try:
            pytz.timezone(new_timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            await ctx.send("Invalid timezone!")
        else:
            await self.config.guild(ctx.guild).timezone_str.set(new_timezone_str)
            await ctx.send(f"Timezone set to: `{new_timezone_str}`")
    
    @_cmd_movie_night.command(name="reminder")
    async def _cmd_set_movie_time(self, ctx: commands.Context):
        """Sets a reminder for when the next time to watch a movie is."""
        async with self.config.guild(ctx.guild).movie_time() as movie_time:
            # TODO
            pass