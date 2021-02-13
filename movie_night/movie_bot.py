import discord
from redbot.core import commands
from redbot.core import Config
from redbot.core import checks

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
            "vote_size": 10,            # Deprecated
            "suggestions": [],
            "timezone_str": "UTC",      # Deprecated
            "movie_time": "0 20 * * 5", # Deprecated
            "next_movie_title": "",     # Deprecated
            "prev_vote_msg_id": -1
        }
        
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        
        self.vote_info = {}
        
    """Helper Functions"""
    async def get_guild_message(self, guild:discord.Guild, message_id:int):
        # TODO: Find a better way of loading messages after a restart, since this would be *very very* bad on a large server
        # Probably, just setting a channel to be the *voting* channel would be easiest, but I'm lazy
        
        for channel in guild.text_channels:
            try:
                msg = await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                #TODO: Find a way to retry this sanely
                continue
            else:
                return msg
        
        return None
    
    async def get_vote_info(self, guild_id: int) -> VoteInfo:
        # If a new structure needs to be made
        if guild_id not in self.vote_info:
            # Create a VoteInfo structure
            self.vote_info[guild_id] = VoteInfo()
            
            # Check if there was a vote happening
            msg = None
            prev_vote_msg_id = await self.config.guild_from_id(guild_id).prev_vote_msg_id()
            if prev_vote_msg_id > 0:
                # Try to get the previous message
                msg = await self.get_guild_message(self.bot.get_guild(guild_id), prev_vote_msg_id)
                
                # Failed to retrieve the message
                if msg is None:
                    # Set the prev_msg id to invalid
                    await self.config.guild_from_id(guild_id).prev_vote_msg_id.set(-1)
                else:
                    # Get the list of suggestions for the server
                    suggestions = await self.config.guild_from_id(guild_id).suggestions()
                    await self.vote_info[guild_id]._set_prev_vote_msg(msg, suggestions)
        
        return self.vote_info[guild_id]
    
    
    """ Listeners """
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, raw_reaction:discord.RawReactionActionEvent):
        if raw_reaction.user_id == self.bot.user.id:
            return
        
        vinfo = await self.get_vote_info(raw_reaction.guild_id)
        
        # Check that the react is on the proper message
        if not vinfo.check_msg_id(raw_reaction.message_id):
            return
        
        await vinfo.reaction_add_listener(raw_reaction)
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, raw_reaction:discord.RawReactionActionEvent):
        if raw_reaction.user_id == self.bot.user.id:
            return
        
        vinfo = await self.get_vote_info(raw_reaction.guild_id)
        
        # Check that the react is on the proper message
        if not vinfo.check_msg_id(raw_reaction.message_id):
            return
        
        await vinfo.reaction_remove_listener(raw_reaction)
    
    
    """Global Commands"""
    
    @commands.command(name="suggest")
    async def _cmd_add_suggestion(self, ctx: commands.Context, movie_title:str, *args):
        """Adds a movie suggestion to the list of possible movies to watch."""
        movie_title = movie_title + " " + " ".join(args)
        
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            # Check that the max number of suggestions isn't reached
            if len(suggestions) >= 20:
                await ctx.send("Maximum number of suggestions has already been reached!")
                return
            
            if movie_title in suggestions:
                await ctx.send(f"\"**{movie_title}**\" is already in the list!")
            else:
                suggestions.append(movie_title)
                await ctx.send(f"\"**{movie_title}**\" has been added to the list of movie suggestions.")
            
            # If a vote is on-going, add the suggestion to the vote list
            vinfo = await self.get_vote_info(ctx.guild.id)
            if vinfo.is_voting_enabled():
                await vinfo.add_voting_option(movie_title)
    
    @commands.command(name="unsuggest")
    async def _cmd_del_suggestion(self, ctx: commands.Context, movie_index:int):
        """Removes a movie suggestion from the list of possible movies to watch. eg. [p]unsuggest 1"""
        # TODO: Only allow users who suggested a movie to un-suggest one (and admins)
        movie_index = movie_index - 1
        
        # If a vote is happening don't allow people to remove suggestions
        vinfo = await self.get_vote_info(ctx.guild.id)
        if vinfo.is_voting_enabled():
            await ctx.send("Cannot remove suggestions while a vote is in progress!")
            return
        
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            if movie_index < 0 or movie_index >= len(suggestions):
                await ctx.send(f"That isn't a valid index, sorry! Please check the current list with: `{ctx.prefix}suggestions`.")
            else:
                movie_name = suggestions.pop(movie_index)
                await ctx.send(f"\"**{movie_name}**\" has been removed from the list of movie suggestions.")
    
    @commands.command(name="suggestions")
    async def _cmd_list_suggestions(self, ctx: commands.Context):
        """Lists all current movie suggestions."""
        suggestions = await self.config.guild(ctx.guild).suggestions()
        suggestions_list = [f"{ind}) {suggestions[ind-1]}\n" for ind in range(1, len(suggestions)+1)]
        suggestions_str = "".join(suggestions_list)
        
        em = discord.Embed(
            title="**Movie Suggestions:**\n",
            description=suggestions_str,
            color=discord.Color.green()
        )
        
        await ctx.send(embed=em)
    
    
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
            ``{0}mn clear_suggestions``: Clears the list of movie suggestions.\n
            ``{0}mn start_vote``: Starts a vote for the next movie to watch.\n
            ``{0}mn stop_vote``: Stops the on-going vote for the next movie to watch.\n
            ``{0}mn cancel_vote``: Cancels the on-going vote.\n
            \n"""
            
            em = discord.Embed(
                title=title,
                description=description.format(prefix),
                color=discord.Color.green()
            )
            
            await ctx.send(embed=em)
    
    @_cmd_movie_night.command(name="clear_suggestions")
    async def _cmd_clear_suggestions(self, ctx: commands.Context):
        """Clears the suggestions list."""
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            suggestions.clear()
            await ctx.send("Suggestions list has been cleared!")
    
    @_cmd_movie_night.command(name="start_vote")
    async def _cmd_start_vote(self, ctx: commands.Context):
        """Starts a vote for choosing the next movie."""
        vinfo = await self.get_vote_info(ctx.guild.id)
        
        suggestions = await self.config.guild(ctx.guild).suggestions()
        
        # Stop the vote if there are no suggestions
        if len(suggestions) <= 0:
            await ctx.send("Cannot run a vote with no suggestions.")
            return
        
        try:
            vote_msg_id = await vinfo.start_vote(suggestions, ctx)
        except VoteException as ve:
            await ctx.send(str(ve))
        else:
            await ctx.send(ctx.guild.default_role.mention + " has started!")
            await self.config.guild(ctx.guild).prev_vote_msg_id.set(vote_msg_id)
    
    @_cmd_movie_night.command(name="stop_vote")
    async def _cmd_stop_vote(self, ctx: commands.Context):
        """Stops the ongoing vote for the next movie (if any)."""
        vinfo = await self.get_vote_info(ctx.guild.id)
        try:
            winner, bad_votes = await vinfo.stop_vote(ctx)
        except VoteException as ve:
            await ctx.send(str(ve))
        else:
            async with self.config.guild(ctx.guild).suggestions() as suggestions:
                # Remove the winner from the list and set it as the next movie title
                # Also remove the "bad votes"
                removal_list = [winner, *bad_votes]
                suggestions = [x for x in suggestions if x not in removal_list]
            
            await self.config.guild(ctx.guild).next_movie_title.set(winner)
        finally:
            await self.config.guild(ctx.guild).prev_vote_msg_id.set(-1)
    
    @_cmd_movie_night.command(name="cancel_vote")
    async def _cmd_cancel_vote(self, ctx: commands.Context):
        """Stops the ongoing vote for the next movie (if any)."""
        vinfo = await self.get_vote_info(ctx.guild.id)
        try:
            await vinfo.cancel_vote()
        except VoteException as ve:
            await ctx.send(str(ve))
        else:
            await ctx.send("Voting cancelled!")
        finally:
            await self.config.guild(ctx.guild).prev_vote_msg_id.set(-1)
