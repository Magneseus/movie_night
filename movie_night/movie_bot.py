import discord
from redbot.core import commands
from redbot.core import Config
from redbot.core import checks

import pytz
from datetime import datetime
from croniter import croniter

from .voteinfo import VoteInfo, VoteException, alphabet

# TODO: Automatic reminder for movie nights

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
            "movie_time": "0 20 * * 5",
            "next_movie_title": "",
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
        # if raw_reaction.user_id == self.bot.user.id:
        #     return
        
        vinfo = await self.get_vote_info(raw_reaction.guild_id)
        
        # Check that the react is on the proper message
        if not vinfo.check_msg_id(raw_reaction.message_id):
            return
        
        await vinfo.reaction_add_listener(raw_reaction)
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, raw_reaction:discord.RawReactionActionEvent):
        # if raw_reaction.user_id == self.bot.user.id:
        #     return
        
        vinfo = await self.get_vote_info(raw_reaction.guild_id)
        
        # Check that the react is on the proper message
        if not vinfo.check_msg_id(raw_reaction.message_id):
            return
        
        await vinfo.reaction_remove_listener(raw_reaction)
    
    
    """Global Commands"""
    
    @commands.command(name="suggest")
    async def _cmd_add_suggestion(self, ctx: commands.Context, movie_title:str, *args):
        """Adds a movie suggestion to the list of possible movies to watch."""
        full_movie_title = movie_title + " " + " ".join(args)
        
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            # Check that the max number of suggestions isn't reached
            if len(suggestions) >= 26:
                await ctx.send("Maximum number of suggestions has already been reached!")
                return
            
            if full_movie_title in suggestions:
                await ctx.send(f"\"**{full_movie_title}**\" is already in the list!")
            else:
                suggestions.append(full_movie_title)
                await ctx.send(f"\"**{full_movie_title}**\" has been added to the list of movie suggestions.")
            
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
    
    ''' Removed for now
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
    '''
    
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
        timezone_str = await self.config.guild(ctx.guild).timezone_str()
        timezone = pytz.timezone(timezone_str)
        
        utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
        local_now = utc_now.astimezone(timezone)
        
        cron_time = await self.config.guild(ctx.guild).movie_time()
        next_movie_time = str(croniter(cron_time, local_now).get_next(datetime))
        
        # TODO: Better formatting for the timestamp
        # Check if < 1 week, if so just say "Friday at 8pm"
        # Otherwise if < 1 yr: 8pm on Friday, May 20th
        # Otherwise: 8pm on Friday, May 20th, 2021
        
        next_movie_title = await self.config.guild(ctx.guild).next_movie_title()
        movie_playing = f"\n**{next_movie_title}** will be playing!" if next_movie_title else ""
        
        await ctx.send(f"The next Movie Night is set for: `{next_movie_time}`{movie_playing}")
    
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
    
    ''' Removed for now
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
    '''
    
    @_cmd_movie_night.command(name="clear_suggestions")
    async def _cmd_clear_suggestions(self, ctx: commands.Context):
        """Clears the suggestions list."""
        async with self.config.guild(ctx.guild).suggestions() as suggestions:
            suggestions.clear()
            await ctx.send("Suggestions list has been cleared!")
    
    ''' Removed for now
    @_cmd_movie_night.command(name="size")
    async def _cmd_size_vote(self, ctx: commands.Context, num_options:int = 10):
        """Sets the maximum number of options when creating a vote."""
        vinfo = await self.get_vote_info(ctx.guild.id)
        
        if vinfo.is_voting_enabled():
            await ctx.send("Cannot change the size of a vote while voting is occurring!")
        elif num_options <= 0 or num_options > 26:
            await ctx.send("Cannot change the size of a vote to a number <= 0 or > 26!")
        else:
            await self.config.guild(ctx.guild).vote_size.set(num_options)
            await ctx.send(f"Maximum number of choices for a vote is now set to: `{num_options}`")
    '''
    
    @_cmd_movie_night.command(name="start_vote")
    async def _cmd_start_vote(self, ctx: commands.Context):
        """Starts a vote for choosing the next movie."""
        vinfo = await self.get_vote_info(ctx.guild.id)
        
        suggestions = await self.config.guild(ctx.guild).suggestions()
        # vote_size = await self.config.guild(ctx.guild).vote_size()
        
        try:
            vote_msg_id = await vinfo.start_vote(suggestions, ctx)
        except VoteException as ve:
            await ctx.send(str(ve))
        else:
            await self.config.guild(ctx.guild).prev_vote_msg_id.set(vote_msg_id)
    
    @_cmd_movie_night.command(name="stop_vote")
    async def _cmd_stop_vote(self, ctx: commands.Context):
        """Stops the ongoing vote for the next movie (if any)."""
        vinfo = await self.get_vote_info(ctx.guild.id)
        try:
            winner = await vinfo.stop_vote(ctx)
        except VoteException as ve:
            await ctx.send(str(ve))
        else:
            # Remove the winner from the list and set it as the next movie title
            async with self.config.guild(ctx.guild).suggestions() as suggestions:
                try:
                    suggestions.remove(winner)
                except ValueError:
                    pass
            
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
    async def _cmd_set_movie_time(self, ctx: commands.Context, new_movie_time:str):
        """Sets a reminder for when the next time to watch a movie is."""
        if not croniter.is_valid(new_movie_time):
            await ctx.send("Invalid cron timestamp!")
            return
        
        await self.config.guild(ctx.guild).movie_time.set(new_movie_time)
        await self._cmd_next_movie(ctx)