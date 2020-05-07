import discord
import difflib

from typing import List, Tuple, Dict
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
        self.fuzzy_match_ratio = 0.4
        
        self._enabled = False
        self._msg = None
        self._choices = []
        self._movie_votes = {}
        self._user_votes  = {}
    
    async def add_user_vote(self, vote:str, uid:str) -> None:
        """
        Applies a given vote from a user.
        
        Allowed formats:
         - "a"
         - "b"
         - "a,b,d"
         - "a movie title that will be searched amongst results"
        """
        num_choices = len(self._choices)
        lvote = vote.lower()
        
        # Make the user vote set, if it doesn't exist already
        if uid not in self._user_votes:
            self._user_votes[uid] = set()
        
        
        # One vote, with one letter
        if len(lvote) == 1 and lvote in alphabet[:num_choices]:
            title = self._get_movie_from_alpha(lvote)
            
            if title is None:
                raise VoteException(f"Invalid voting option: `{lvote}`")
            
            if title in self._user_votes[uid]:
                raise VoteException("You have already voted for that option!")
            
            self._apply_vote(title, uid)
            await self.update_vote_message(None)
            return
        
        
        # Maybe a title?
        # TODO: Use something like Levenshtein instead of simple sub-string comparisons
        max_ratio = 0
        index = -1
        comparison = difflib.SequenceMatcher(None, lvote, "")
        
        for i in range(num_choices):
            comparison.set_seq2(self._choices[i])
            ratio = comparison.quick_ratio()
            
            if ratio > max_ratio:
                max_ratio = ratio
                index = i
        
        if max_ratio > self.fuzzy_match_ratio:
            # We have a good match! 
            self._apply_vote(self._choices[index], uid)
            await self.update_vote_message(None)
            return
        
        
        # Multiple votes, each one letter
        commas = set(lvote[1::2])
        if len(commas) == 1 and ',' in commas:
            votes = sorted(lvote[::2])
            duplicates = set(votes)
            
            if len(duplicates) != len(votes):
                raise VoteException("Vote list cannot contain duplicates!")
            
            if not duplicates.issubset(alphaset):
                raise VoteException("Vote list can only contain letters!")
            
            titles_to_vote_for = []
            for _vote in votes:
                title = self._get_movie_from_alpha(_vote)
                if title is None:
                    raise VoteException(f"Invalid voting option: `{_vote}`")
                
                titles_to_vote_for.append(title)
            
            # NOTE: We will choose to silently ignore any duplicate votes for this type of voting
            for _title in titles_to_vote_for:
                self._apply_vote(_title, uid)
            
            await self.update_vote_message(None)
    
    async def start_vote(self, choices:List[str], ctx:discord.ext.commands.Context) -> None:
        """Starts a new vote and posts a new vote message to the chat in the given context"""
        if self._enabled:
            raise VoteException("Voting has already started!")
        
        self._enabled = True
        await self._clear_vote()
        
        self._choices = choices
        
        for i in range(len(self._choices)):
            # Generate movie_vote
            key = self._choices[i] # title
            entry = {
                "title": key, # title
                "alpha": alphabet[i], # alphabetical indicator
                "votes": set() # set of user ids
            }
            
            self._movie_votes[key] = entry
        
        await self.update_vote_message(ctx)
        
        try:
            await self._msg.pin()
        except (discord.Forbidden, discord.NotFound):
            pass
        except discord.HTTPException:
            # TODO: Log this
            raise VoteException("Unknown error occurred when pinning vote!")
    
    async def stop_vote(self, ctx:discord.ext.commands.Context) -> str:
        """
        Stops a vote, 
        updates the vote message with the final results,
        and returns the name of the winning vote
        """
        if not self._enabled:
            raise VoteException("Voting hasn't started!")
        
        self._enabled = False
        winner = self._sorted_movie_votes()[0]
        num_votes = len(winner['votes'])
        
        await self._clear_msg()
        await self.update_vote_message(ctx, sort_list=True)
        await ctx.send(F"The winner of the vote, with {num_votes}, is: **{winner['title']}**")
        
        return winner['title']
    
    async def cancel_vote(self) -> None:
        """Stops a vote and does not post any results"""
        if not self._enabled:
            raise VoteException("Voting hasn't started!")
        
        self._enabled = False
        await self._clear_vote()
    
    async def update_vote_message(self, ctx:discord.ext.commands.Context, sort_list:bool=False) -> None:
        """Creates a new (or updates the current) vote message in a given context"""
        sorted_votes = self._sorted_movie_votes()
        max_votes = len(sorted_votes[0]['votes'])
        
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
            if self._msg is None:
                self._msg = await ctx.send(content=content)
                
            else:
                await self._msg.edit(content=content)
        except discord.Forbidden:
            # TODO: message the user?
            raise VoteException("Unable to send message in the given context.")
        except discord.HTTPException:
            # TODO: log this
            raise VoteException("Unknown error occurred!")
        
        # TODO: add reactions
    
    def is_voting_enabled(self) -> bool:
        return self._enabled
    
    """ Private methods """
    
    async def _clear_vote(self) -> None:
        await self._clear_msg()
        
        self._choices = []
        self._movie_votes = {}
        self._user_votes = {}
        self._result = ""
    
    async def _clear_msg(self) -> None:
        if self._msg is not None:
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
        self._user_votes[uid].add(title)
        self._movie_votes[title]['votes'].add(uid)