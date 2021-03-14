import discord
import random

from typing import List, Tuple, Dict, Optional
from functools import cmp_to_key

alphabet = 'a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z'.split(',')
alphaset = set(alphabet)
alpha_to_num = {alphabet[i]: i for i in range(len(alphabet))}

class VoteException(Exception):
    pass

class VoteInfo:
    """Class for running a vote with a given list of choices"""
    def __init__(self):
        self.vote_bar_filled = '█'
        self.vote_bar_empty = '░'
        self.fuzzy_match_ratio = 0.5
        
        self._enabled = False
        self._msg = None
        self._choices = []
        self._movie_votes = {}
        self._user_votes  = {}
        
        self.pin_vote = False
        
        self.alpha_emoji = [VoteInfo.gen_alpha_emoji(i) for i in range(26)]
    
    async def start_vote(self, choices:List[str], ctx:discord.ext.commands.Context) -> int:
        """Starts a new vote and posts a new vote message to the chat in the given context"""
        if self._enabled:
            raise VoteException("Voting has already started!")
        
        self._enabled = True
        await self._clear_vote()
        
        self._choices = choices
        self._create_vote_structures()
        
        await self.update_vote_message(ctx)
        
        if self.pin_vote:
            try:
                await self._msg.pin()
            except (discord.Forbidden, discord.NotFound):
                pass
            except discord.HTTPException:
                # TODO: Log this
                raise VoteException("Unknown error occurred when pinning vote!")
        
        for i in range(len(self._choices)):
            await self._msg.add_reaction(self.alpha_emoji[i])
        
        return self._msg.id
    
    async def stop_vote(self, ctx:discord.ext.commands.Context) -> Tuple[str, Optional[List[str]]]:
        """
        Stops a vote, 
        updates the vote message with the final results,
        and returns the name of the winning vote as well as
        the names of all low-voted options
        """
        if not self._enabled:
            raise VoteException("Voting hasn't started!")
        
        self._enabled = False
        
        sorted_movie_list = self._sorted_movie_votes()
        num_votes = len(sorted_movie_list[0]['votes'])
        winner = sorted_movie_list[0]
        tie_text = ""
        
        # Check if there is a tie and handle this with a random selection
        if len(sorted_movie_list) > 1 and len(sorted_movie_list[1]['votes']) == num_votes:
            tie_list = [movie for movie in sorted_movie_list if len(movie['votes']) == num_votes]
            winner = random.choice(tie_list)
            
            tie_text = "**, **".join([movie['title'] for movie in tie_list[:-1]])
            tie_text = F"**{tie_text}**, and **{tie_list[-1]['title']}** were tied."
        
        # Get a list of movies to remove
        bad_votes = [movie['title'] for movie in sorted_movie_list if len(movie['votes']) <= 1]
        loss_text = ""
        
        # Check if there are any movies to remove, and if so make some text listing them
        if len(bad_votes) > 1:
            loss_text = "**, **".join(bad_votes[:-1])
            loss_text = F"Movies with only one vote or less, to be removed: **{loss_text}**, and **{bad_votes[-1]}**."
        elif len(bad_votes) == 1:
            loss_text = F"Movie with only one vote or less, to be removed: **{bad_votes[0]}**."
        
        await self._clear_msg()
        await self.update_vote_message(ctx, sort_list=True)
        await ctx.send(F"The winner of the vote, with {num_votes}, is: **{winner['title']}**.\n{tie_text}\n\n{loss_text}")
        
        return (winner['title'], bad_votes)
    
    async def cancel_vote(self) -> None:
        """Stops a vote and does not post any results"""
        if not self._enabled:
            raise VoteException("Voting hasn't started!")
        
        self._enabled = False
        await self._clear_vote()
    
    async def update_vote_message(self, ctx:discord.ext.commands.Context, sort_list:bool=False) -> None:
        """Creates a new (or updates the current) vote message in a given context"""
        sorted_votes = self._sorted_movie_votes()
        max_votes = len(sorted_votes[0]['votes']) if len(sorted_votes) > 0 else 0
        
        title = "**Movie Vote:**\n"
        border = "= = = = ="
        msg = []
        
        entry_list = sorted_votes if sort_list else self._movie_votes.values()
        
        for entry in entry_list:
            num_votes = len(entry['votes'])
            
            frac_vote = float(num_votes) / float(max_votes) if max_votes > 0 else 0
            frac_vote = int(frac_vote * 20.0)
            
            bar_fill = self.vote_bar_filled * frac_vote
            bar_empty = self.vote_bar_empty * (20 - frac_vote)
            
            entry_title = entry['title']
            alpha = entry['alpha']
            icon = f":regional_indicator_{alpha}:"
            
            msg.append(f"{bar_fill}{bar_empty}{icon} - **{entry_title}** ({num_votes})")
        
        content = title + border + "\n" + "\n".join(msg) + "\n" + border
        
        """
        em = discord.Embed(
            title=title,
            description=content,
            color=discord.Color.green()
        )
        """
        
        try:
            if self._msg is None and ctx is not None:
                self._msg = await ctx.send(content=content)
            else:
                await self._msg.edit(content=content)
        except discord.Forbidden:
            # TODO: message the user?
            raise VoteException("Unable to send message in the given context.")
        except discord.HTTPException:
            # TODO: log this
            raise VoteException("Unknown error occurred!")
    
    async def add_voting_option(self, movie_title:str) -> None:
        """Add a new voting option to the vote, while vote is happening"""
        index = len(self._choices)
        
        # Add to the list of choices
        self._choices.append(movie_title)
        
        # Create an entry in the voting structures
        self._add_vote_structure(movie_title, index)
        
        # Update the voting message
        await self.update_vote_message(None)
        
        # Add a react to the message
        await self._msg.add_reaction(self.alpha_emoji[index])
        
    def is_voting_enabled(self) -> bool:
        return self._enabled
    
    async def reaction_add_listener(self, raw_reaction:discord.RawReactionActionEvent) -> None:
        if not self._enabled:
            return
        
        offset = VoteInfo.get_alpha_offset_from_emoji(raw_reaction.emoji)
        if offset == -1 or offset >= len(self._choices):
            return
        
        self._apply_vote(self._choices[offset], raw_reaction.user_id)
        
        # TODO: Apply a timer or something for larger servers (same for reaction adding/removing)
        await self.update_vote_message(None)
        
    async def reaction_remove_listener(self, raw_reaction:discord.RawReactionActionEvent) -> None:
        if not self._enabled:
            return
        
        offset = VoteInfo.get_alpha_offset_from_emoji(raw_reaction.emoji)
        if offset == -1 or offset >= len(self._choices):
            return
        
        self._remove_vote(self._choices[offset], raw_reaction.user_id)
        
        # TODO: Apply a timer or something for larger servers (same for reaction adding/removing)
        await self.update_vote_message(None)
    
    def check_msg_id(self, id:int) -> bool:
        return self._msg is not None and id == self._msg.id
    
    """ Private methods """
    
    def _create_vote_structures(self) -> None:
        for i in range(len(self._choices)):
            # Generate movie_vote
            key = self._choices[i] # title
            self._add_vote_structure(key, i)
    
    def _add_vote_structure(self, key, index) -> None:
        entry = {
            "title": key, # title
            "alpha": alphabet[index], # alphabetical indicator
            "votes": set() # set of user ids
        }
        
        self._movie_votes[key] = entry
    
    async def _set_prev_vote_msg(self, prev_vote_msg:discord.Message, suggestions:List[str]) -> None:
        if prev_vote_msg is not None:
            # If there is a previous vote (ie. the bot shutdown, or crashed)
            # get the votes that are currently on the message
            
            # Set the current message
            self._msg = prev_vote_msg
            
            # Create vote structures with the given choices
            self._choices = suggestions
            self._create_vote_structures()
            
            # Get the reactions (votes)
            for react in prev_vote_msg.reactions:
                async for user in react.users():
                    offset = VoteInfo.get_alpha_offset_from_emoji(react.emoji)
                    if offset == -1 or offset >= len(self._choices):
                        continue
                    
                    self._apply_vote(self._choices[offset], user.id)
            
            # Set voting enabled
            self._enabled = True
            
            # Update the message
            await self.update_vote_message(None)
    
    async def _clear_vote(self) -> None:
        await self._clear_msg()
        
        self._choices = []
        self._movie_votes = {}
        self._user_votes = {}
        self._result = ""
    
    async def _clear_msg(self) -> None:
        if self._msg is not None:
            if self.pin_vote:
                try:
                    await self._msg.unpin()
                except (discord.Forbidden, discord.NotFound):
                    pass
                except discord.HTTPException:
                    # TODO: Log this
                    self._enabled = False
                    raise VoteException("Unknown error occurred!")
                
            self._msg = None
    
    def _sorted_movie_votes(self) -> List[Dict]:
        return sorted(self._movie_votes.values(), key=cmp_to_key(lambda x, y: len(y['votes']) - len(x['votes'])))
    
    def _get_movie_from_alpha(self, alpha:str) -> str:
        if alpha not in alphaset:
            return None
        
        index = alpha_to_num[alpha]
        if index >= len(self._choices):
            return None
        
        return self._choices[index]
    
    def _apply_vote(self, title:str, uid:str) -> None:
        # Make the user vote set, if it doesn't exist already
        if uid not in self._user_votes:
            self._user_votes[uid] = set()
        
        self._user_votes[uid].add(title)
        self._movie_votes[title]['votes'].add(uid)
    
    def _remove_vote(self, title:str, uid:str) -> None:
        self._user_votes[uid].remove(title)
        self._movie_votes[title]['votes'].remove(uid)
    
    @staticmethod
    def gen_alpha_emoji(offset:int) -> str:
        if offset < 0 or offset >= 26:
            return ''
        
        start = b'\xff\xfe<\xd8'
        middle = b'\xe6'
        end = b'\xdd'
        
        final = start + bytes([middle[0] + offset]) + end
        
        return final.decode('utf-16')
        
    @staticmethod
    def get_alpha_offset_from_emoji(emoji:discord.Emoji) -> int:
        if (isinstance(emoji, discord.PartialEmoji)):
            offset = ord(emoji.name) - 127462
        else:
            offset = ord(emoji) - 127462
        
        if offset < 0 or offset >= 26:
            return -1
        
        return offset
    
