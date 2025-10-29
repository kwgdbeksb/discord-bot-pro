import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
import logging

# Set up logging for the football cog
logger = logging.getLogger(__name__)


class FootballGameError(Exception):
    """Custom exception for football game errors."""
    pass


class FootballGame:
    """Represents a football game between two players with enhanced mechanics."""
    
    def __init__(self, player1: discord.Member, player2: discord.Member):
        self.player1 = player1
        self.player2 = player2
        self.score = [0, 0]  # [player1_score, player2_score]
        self.ball_position = 5  # 0-10, where 5 is center, 0 is player1's goal, 10 is player2's goal
        self.current_player = player1  # Who has the ball
        self.game_time = 0  # Game time in rounds
        self.max_time = 15  # Increased game length for better gameplay
        self.is_active = True
        self.last_action = "⚽ Game started! Ball is at center field."
        self.created_at = datetime.now()
        self.action_history: List[str] = []
        self.consecutive_fails = 0  # Track consecutive failed actions
        
    def get_field_display(self) -> str:
        """Generate enhanced ASCII representation of the football field."""
        field = ["⬜"] * 11
        
        # Add goals with better visualization
        field[0] = "🥅"  # Player 1's goal
        field[10] = "🥅"  # Player 2's goal
        
        # Add center line marker
        if self.ball_position != 5:
            field[5] = "⚪"  # Center line
        
        # Add ball position with player indicator
        if self.current_player == self.player1:
            field[self.ball_position] = "🔵"  # Blue ball for player 1
        else:
            field[self.ball_position] = "🔴"  # Red ball for player 2
        
        # Create field display with position numbers
        field_str = "".join(field)
        numbers = "0123456789🔟"
        
        return f"""
🏟️ **FOOTBALL FIELD** 🏟️
```
{self.player1.display_name[:12]:<12} vs {self.player2.display_name[:12]:>12}
```
{field_str}
```
{numbers}
Position: {self.ball_position}/10 | Ball Control: {self.current_player.display_name}
```
        """
    
    def get_game_info(self) -> discord.Embed:
        """Create an enhanced embed with current game information."""
        # Determine embed color based on game state
        if not self.is_active:
            color = 0xff6b6b  # Red for finished games
        elif self.ball_position <= 2:
            color = 0x4ecdc4  # Teal for player 1's side
        elif self.ball_position >= 8:
            color = 0xffe66d  # Yellow for player 2's side
        else:
            color = 0x95e1d3  # Green for center field
        
        embed = discord.Embed(
            title="⚽ Football Championship",
            description=self.get_field_display(),
            color=color,
            timestamp=datetime.now()
        )
        
        # Score with visual indicators
        score_display = f"🔵 {self.player1.display_name}: **{self.score[0]}** goals\n🔴 {self.player2.display_name}: **{self.score[1]}** goals"
        embed.add_field(
            name="📊 Score",
            value=score_display,
            inline=True
        )
        
        # Enhanced time display
        time_remaining = self.max_time - self.game_time
        time_display = f"Round **{self.game_time + 1}**/{self.max_time}\n⏰ {time_remaining} rounds left"
        embed.add_field(
            name="⏱️ Game Progress",
            value=time_display,
            inline=True
        )
        
        # Current turn with action hint
        turn_display = f"🎯 **{self.current_player.display_name}**\n{'🔵' if self.current_player == self.player1 else '🔴'} Your turn!"
        embed.add_field(
            name="🎮 Current Turn",
            value=turn_display,
            inline=True
        )
        
        # Last action with better formatting
        embed.add_field(
            name="📝 Last Action",
            value=f"```{self.last_action}```",
            inline=False
        )
        
        # Game result
        if not self.is_active:
            winner = self.get_winner()
            if winner:
                embed.add_field(
                    name="🏆 WINNER!",
                    value=f"🎉 **{winner.display_name}** wins the match!\nFinal Score: {self.score[0]} - {self.score[1]}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🤝 DRAW!",
                    value=f"It's a tie! Both players scored {self.score[0]} goals.",
                    inline=False
                )
        
        # Add game statistics
        if self.game_time > 0:
            total_actions = len(self.action_history)
            embed.set_footer(text=f"Total actions: {total_actions} | Game duration: {(datetime.now() - self.created_at).seconds}s")
        
        return embed
    
    def get_winner(self) -> Optional[discord.Member]:
        """Determine the winner of the game."""
        if self.score[0] > self.score[1]:
            return self.player1
        elif self.score[1] > self.score[0]:
            return self.player2
        return None
    
    def _calculate_success_rate(self, base_rate: int, action: str) -> int:
        """Calculate dynamic success rate based on game state."""
        success_rate = base_rate
        
        # Reduce success rate for consecutive failures to prevent frustration
        if self.consecutive_fails >= 2:
            success_rate += 10  # Boost success rate after multiple fails
        
        # Position-based modifiers
        if action == "kick":
            # Harder to kick near goals (more pressure)
            if self.ball_position <= 2 or self.ball_position >= 8:
                success_rate -= 10
        elif action == "defend":
            # Easier to defend near your own goal
            if (self.current_player == self.player1 and self.ball_position <= 3) or \
               (self.current_player == self.player2 and self.ball_position >= 7):
                success_rate += 15
        
        return max(30, min(95, success_rate))  # Clamp between 30-95%
    
    def perform_action(self, action: str) -> Tuple[str, bool]:
        """Perform a football action and return the result and success status."""
        if not self.is_active:
            raise FootballGameError("Game is not active!")
        
        success_chance = random.randint(1, 100)
        result = ""
        action_successful = False
        
        if action == "kick":
            success_rate = self._calculate_success_rate(70, "kick")
            if success_chance <= success_rate:
                action_successful = True
                move_distance = random.randint(2, 4)  # More powerful kicks
                
                if self.current_player == self.player1:
                    old_pos = self.ball_position
                    self.ball_position = min(10, self.ball_position + move_distance)
                    
                    if self.ball_position == 10:
                        self.score[0] += 1
                        result = f"⚽ GOOOAL! {self.player1.display_name} scores with a powerful kick!"
                        self.ball_position = 5  # Reset to center
                    else:
                        result = f"🦵 {self.player1.display_name} kicks the ball forward {move_distance} positions! ({old_pos} → {self.ball_position})"
                else:
                    old_pos = self.ball_position
                    self.ball_position = max(0, self.ball_position - move_distance)
                    
                    if self.ball_position == 0:
                        self.score[1] += 1
                        result = f"⚽ GOOOAL! {self.player2.display_name} scores with a powerful kick!"
                        self.ball_position = 5  # Reset to center
                    else:
                        result = f"🦵 {self.player2.display_name} kicks the ball forward {move_distance} positions! ({old_pos} → {self.ball_position})"
            else:
                result = f"❌ {self.current_player.display_name} missed the kick! Ball stays at position {self.ball_position}."
                
        elif action == "pass":
            success_rate = self._calculate_success_rate(85, "pass")
            if success_chance <= success_rate:
                action_successful = True
                move_distance = random.randint(1, 3)
                
                if self.current_player == self.player1:
                    old_pos = self.ball_position
                    self.ball_position = min(10, self.ball_position + move_distance)
                    
                    if self.ball_position == 10:
                        self.score[0] += 1
                        result = f"⚽ GOAL! {self.player1.display_name} scores with a perfect pass!"
                        self.ball_position = 5
                    else:
                        result = f"🎯 {self.player1.display_name} makes a successful pass! ({old_pos} → {self.ball_position})"
                else:
                    old_pos = self.ball_position
                    self.ball_position = max(0, self.ball_position - move_distance)
                    
                    if self.ball_position == 0:
                        self.score[1] += 1
                        result = f"⚽ GOAL! {self.player2.display_name} scores with a perfect pass!"
                        self.ball_position = 5
                    else:
                        result = f"🎯 {self.player2.display_name} makes a successful pass! ({old_pos} → {self.ball_position})"
            else:
                # Ball changes possession on failed pass
                self.current_player = self.player2 if self.current_player == self.player1 else self.player1
                result = f"❌ Pass intercepted by {self.current_player.display_name}! Ball control changes!"
                action_successful = False  # Interception is not a success for the passer
                
        elif action == "defend":
            success_rate = self._calculate_success_rate(65, "defend")
            if success_chance <= success_rate:
                action_successful = True
                move_distance = random.randint(1, 3)
                
                # Defensive move pulls ball back towards your own goal
                if self.current_player == self.player1:
                    old_pos = self.ball_position
                    self.ball_position = max(0, self.ball_position - move_distance)
                    result = f"🛡️ {self.player1.display_name} successfully defends! Ball pulled back ({old_pos} → {self.ball_position})"
                else:
                    old_pos = self.ball_position
                    self.ball_position = min(10, self.ball_position + move_distance)
                    result = f"🛡️ {self.player2.display_name} successfully defends! Ball pulled back ({old_pos} → {self.ball_position})"
            else:
                result = f"❌ {self.current_player.display_name}'s defense failed! Ball stays at position {self.ball_position}."
        
        # Update consecutive fails counter
        if action_successful:
            self.consecutive_fails = 0
        else:
            self.consecutive_fails += 1
        
        self.last_action = result
        self.action_history.append(f"Round {self.game_time + 1}: {result}")
        
        # Switch turns (except on interception where turn already switched)
        if "intercepted" not in result and "GOAL" not in result:
            self.current_player = self.player2 if self.current_player == self.player1 else self.player1
        elif "GOAL" in result:
            # After a goal, the player who was scored on gets the ball
            self.current_player = self.player2 if "scores" in result and self.player1.display_name in result else self.player1
        
        # Advance game time
        self.game_time += 1
        
        # Check if game is over
        if self.game_time >= self.max_time:
            self.is_active = False
            if self.get_winner():
                self.last_action += f"\n🏁 Game Over! {self.get_winner().display_name} wins!"
            else:
                self.last_action += "\n🏁 Game Over! It's a draw!"
        
        return result, action_successful


class FootballView(discord.ui.View):
    """Enhanced view for football game interactions."""
    
    def __init__(self, game: FootballGame, cog: 'Football'):
        super().__init__(timeout=600)  # 10 minute timeout
        self.game = game
        self.cog = cog
        self.update_button_styles()
    
    def update_button_styles(self):
        """Update button styles based on game state."""
        if not self.game.is_active:
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
            return
        
        # Update button styles based on position and current player
        for item in self.children:
            if hasattr(item, 'custom_id'):
                if item.custom_id == "kick":
                    # Make kick button more prominent when near goal
                    if (self.game.current_player == self.game.player1 and self.game.ball_position >= 7) or \
                       (self.game.current_player == self.game.player2 and self.game.ball_position <= 3):
                        item.style = discord.ButtonStyle.danger  # Red for scoring opportunity
                    else:
                        item.style = discord.ButtonStyle.primary
                elif item.custom_id == "defend":
                    # Make defend button prominent when in danger
                    if (self.game.current_player == self.game.player1 and self.game.ball_position <= 3) or \
                       (self.game.current_player == self.game.player2 and self.game.ball_position >= 7):
                        item.style = discord.ButtonStyle.success  # Green for defensive opportunity
                    else:
                        item.style = discord.ButtonStyle.secondary
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enhanced interaction validation."""
        try:
            if interaction.user not in [self.game.player1, self.game.player2]:
                await interaction.response.send_message(
                    "❌ You're not playing in this game! Use `/football @friend` to start your own match.", 
                    ephemeral=True
                )
                return False
            
            if interaction.user != self.game.current_player:
                await interaction.response.send_message(
                    f"❌ It's **{self.game.current_player.display_name}**'s turn! Please wait for your turn.", 
                    ephemeral=True
                )
                return False
            
            if not self.game.is_active:
                await interaction.response.send_message(
                    "❌ This game has ended! Use `/football @friend` to start a new match.", 
                    ephemeral=True
                )
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error in interaction_check: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.", 
                ephemeral=True
            )
            return False
    
    @discord.ui.button(label="🦵 Kick", style=discord.ButtonStyle.primary, custom_id="kick")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            result, success = self.game.perform_action("kick")
            self.update_button_styles()
            embed = self.game.get_game_info()
            
            await interaction.response.edit_message(embed=embed, view=self)
            
            # Clean up if game ended
            if not self.game.is_active:
                await self._cleanup_game(interaction.channel_id)
                
        except Exception as e:
            logger.error(f"Error in kick_button: {e}")
            await interaction.response.send_message("❌ An error occurred during the kick.", ephemeral=True)
    
    @discord.ui.button(label="🎯 Pass", style=discord.ButtonStyle.secondary, custom_id="pass")
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            result, success = self.game.perform_action("pass")
            self.update_button_styles()
            embed = self.game.get_game_info()
            
            await interaction.response.edit_message(embed=embed, view=self)
            
            if not self.game.is_active:
                await self._cleanup_game(interaction.channel_id)
                
        except Exception as e:
            logger.error(f"Error in pass_button: {e}")
            await interaction.response.send_message("❌ An error occurred during the pass.", ephemeral=True)
    
    @discord.ui.button(label="🛡️ Defend", style=discord.ButtonStyle.secondary, custom_id="defend")
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            result, success = self.game.perform_action("defend")
            self.update_button_styles()
            embed = self.game.get_game_info()
            
            await interaction.response.edit_message(embed=embed, view=self)
            
            if not self.game.is_active:
                await self._cleanup_game(interaction.channel_id)
                
        except Exception as e:
            logger.error(f"Error in defend_button: {e}")
            await interaction.response.send_message("❌ An error occurred during the defense.", ephemeral=True)
    
    @discord.ui.button(label="❌ Forfeit", style=discord.ButtonStyle.danger, custom_id="forfeit")
    async def forfeit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Award win to the other player
            if interaction.user == self.game.player1:
                self.game.score[1] += 2  # Reduced forfeit penalty
                winner = self.game.player2
            else:
                self.game.score[0] += 2
                winner = self.game.player1
            
            self.game.is_active = False
            self.game.last_action = f"🏳️ {interaction.user.display_name} forfeited! {winner.display_name} wins by forfeit!"
            
            self.update_button_styles()
            embed = self.game.get_game_info()
            
            await interaction.response.edit_message(embed=embed, view=self)
            await self._cleanup_game(interaction.channel_id)
            
        except Exception as e:
            logger.error(f"Error in forfeit_button: {e}")
            await interaction.response.send_message("❌ An error occurred during forfeit.", ephemeral=True)
    
    async def _cleanup_game(self, channel_id: int):
        """Clean up the game from active games."""
        if channel_id in self.cog.active_games:
            del self.cog.active_games[channel_id]
    
    async def on_timeout(self):
        """Handle view timeout with better cleanup."""
        try:
            self.game.is_active = False
            self.game.last_action = "⏰ Game timed out due to inactivity."
            
            for item in self.children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
        except Exception as e:
            logger.error(f"Error in on_timeout: {e}")


class Football(commands.Cog):
    """Enhanced football game cog for multiplayer football matches."""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_games: Dict[int, FootballGame] = {}  # channel_id -> game
        self.game_stats: Dict[int, Dict] = {}  # user_id -> stats
    
    def _get_user_stats(self, user_id: int) -> Dict:
        """Get or create user statistics."""
        if user_id not in self.game_stats:
            self.game_stats[user_id] = {
                'games_played': 0,
                'games_won': 0,
                'goals_scored': 0,
                'total_actions': 0
            }
        return self.game_stats[user_id]
    
    def _update_user_stats(self, game: FootballGame):
        """Update user statistics after a game."""
        try:
            # Update stats for both players
            p1_stats = self._get_user_stats(game.player1.id)
            p2_stats = self._get_user_stats(game.player2.id)
            
            p1_stats['games_played'] += 1
            p2_stats['games_played'] += 1
            
            p1_stats['goals_scored'] += game.score[0]
            p2_stats['goals_scored'] += game.score[1]
            
            p1_stats['total_actions'] += len(game.action_history) // 2
            p2_stats['total_actions'] += len(game.action_history) // 2
            
            winner = game.get_winner()
            if winner:
                winner_stats = self._get_user_stats(winner.id)
                winner_stats['games_won'] += 1
                
        except Exception as e:
            logger.error(f"Error updating user stats: {e}")
    
    @app_commands.command(name="football", description="Start a multiplayer football game!")
    @app_commands.describe(opponent="The player you want to play football with")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def football(self, interaction: discord.Interaction, opponent: discord.User):
        """Start an enhanced football game with another player."""
        
        try:
            # Enhanced validation
            if interaction.user == opponent:
                embed = discord.Embed(
                    title="❌ Invalid Opponent",
                    description="You can't play football with yourself! Challenge a friend to play.",
                    color=0xff6b6b
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if opponent.bot:
                embed = discord.Embed(
                    title="❌ Invalid Opponent",
                    description="You can't play football with a bot! Challenge a real player.",
                    color=0xff6b6b
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if interaction.channel_id in self.active_games:
                current_game = self.active_games[interaction.channel_id]
                embed = discord.Embed(
                    title="❌ Game In Progress",
                    description=f"There's already a football game between **{current_game.player1.display_name}** and **{current_game.player2.display_name}** in this channel!",
                    color=0xff6b6b
                )
                embed.add_field(
                    name="Current Score",
                    value=f"{current_game.player1.display_name}: {current_game.score[0]} - {current_game.score[1]} :{current_game.player2.display_name}",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Create new enhanced game
            game = FootballGame(interaction.user, opponent)
            self.active_games[interaction.channel_id] = game
            
            # Create enhanced game view
            view = FootballView(game, self)
            
            # Create enhanced initial embed
            embed = game.get_game_info()
            embed.add_field(
                name="🎮 How to Play",
                value="• **🦵 Kick**: Powerful forward move (70% success, 2-4 positions)\n"
                      "• **🎯 Pass**: Safe forward movement (85% success, 1-3 positions)\n"
                      "• **🛡️ Defend**: Pull the ball back defensively (65% success, 1-3 positions)\n"
                      "• **❌ Forfeit**: Give up and end the game (opponent gets 2 points)\n\n"
                      f"**{opponent.mention}**, you've been challenged to a football championship!",
                inline=False
            )
            
            embed.add_field(
                name="🏆 Match Info",
                value=f"**Duration**: 15 rounds\n**Started by**: {interaction.user.mention}\n**Field**: 11 positions (0-10)",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, view=view)
            
            # Enhanced cleanup with statistics update
            await asyncio.sleep(600)  # 10 minutes
            if interaction.channel_id in self.active_games:
                finished_game = self.active_games[interaction.channel_id]
                if not finished_game.is_active:
                    self._update_user_stats(finished_game)
                del self.active_games[interaction.channel_id]
                
        except Exception as e:
            logger.error(f"Error in football command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while starting the game. Please try again.", 
                ephemeral=True
            )
    
    @app_commands.command(name="football_stats", description="View football game statistics")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def football_stats(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """Display enhanced football game statistics."""
        
        try:
            target_user = user or interaction.user
            
            # Current game stats
            if interaction.channel_id in self.active_games:
                game = self.active_games[interaction.channel_id]
                embed = game.get_game_info()
                embed.title = "📊 Current Game Stats"
                
                # Add action history
                if game.action_history:
                    recent_actions = game.action_history[-3:]  # Last 3 actions
                    history_text = "\n".join(recent_actions)
                    embed.add_field(
                        name="📜 Recent Actions",
                        value=f"```{history_text}```",
                        inline=False
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                # User statistics
                stats = self._get_user_stats(target_user.id)
                
                embed = discord.Embed(
                    title=f"📊 Football Statistics - {target_user.display_name}",
                    color=0x4ecdc4,
                    timestamp=datetime.now()
                )
                
                embed.add_field(
                    name="🎮 Games",
                    value=f"**Played**: {stats['games_played']}\n**Won**: {stats['games_won']}\n**Win Rate**: {(stats['games_won']/max(1, stats['games_played'])*100):.1f}%",
                    inline=True
                )
                
                embed.add_field(
                    name="⚽ Performance",
                    value=f"**Goals**: {stats['goals_scored']}\n**Actions**: {stats['total_actions']}\n**Avg Goals/Game**: {(stats['goals_scored']/max(1, stats['games_played'])):.1f}",
                    inline=True
                )
                
                embed.set_thumbnail(url=target_user.display_avatar.url)
                embed.add_field(
                    name="🏆 Rank",
                    value="🥉 Bronze Player" if stats['games_won'] < 5 else "🥈 Silver Player" if stats['games_won'] < 15 else "🥇 Gold Player",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in football_stats command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while fetching statistics.", 
                ephemeral=True
            )
    
    @app_commands.command(name="football_rules", description="Learn how to play football")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def football_rules(self, interaction: discord.Interaction):
        """Display enhanced football game rules and instructions."""
        
        try:
            embed = discord.Embed(
                title="⚽ Football Championship Rules",
                description="Master the art of digital football!",
                color=0x95e1d3,
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="🎯 Objective",
                value="Score more goals than your opponent by moving the ball to their goal line (position 0 or 10).",
                inline=False
            )
            
            embed.add_field(
                name="🎮 Actions & Success Rates",
                value="• **🦵 Kick**: Aggressive move (70% base success, 2-4 positions)\n"
                      "• **🎯 Pass**: Controlled move (85% base success, 1-3 positions)\n"
                      "• **🛡️ Defend**: Defensive move (65% base success, 1-3 positions)\n"
                      "• **❌ Forfeit**: Surrender (opponent gets 2 bonus points)",
                inline=False
            )
            
            embed.add_field(
                name="🏟️ Field Mechanics",
                value="• **Positions**: 0 (Player 1's goal) ↔ 10 (Player 2's goal)\n"
                      "• **Starting Position**: Center field (position 5)\n"
                      "• **After Goals**: Ball resets to center\n"
                      "• **Ball Control**: Indicated by colored ball (🔵/🔴)",
                inline=False
            )
            
            embed.add_field(
                name="⚡ Advanced Features",
                value="• **Dynamic Success Rates**: Based on position and recent performance\n"
                      "• **Interceptions**: Failed passes change ball control\n"
                      "• **Pressure System**: Harder actions near goal areas\n"
                      "• **Comeback Mechanic**: Better odds after consecutive failures",
                inline=False
            )
            
            embed.add_field(
                name="⏱️ Game Rules",
                value="• **Duration**: 15 rounds (increased from 10)\n"
                      "• **Turn System**: Players alternate after each action\n"
                      "• **Timeout**: Games auto-end after 10 minutes of inactivity\n"
                      "• **Statistics**: All games are tracked for leaderboards",
                inline=False
            )
            
            embed.add_field(
                name="🏆 Winning Conditions",
                value="• **Most Goals**: Player with highest score wins\n"
                      "• **Draws**: Possible when scores are equal\n"
                      "• **Forfeit**: Opponent receives 2 bonus points\n"
                      "• **Timeout**: Current score determines winner",
                inline=False
            )
            
            embed.set_footer(text="Use /football @opponent to start a championship match!")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in football_rules command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while loading the rules.", 
                ephemeral=True
            )


async def setup(bot):
    """Setup function to add the Football cog to the bot."""
    try:
        cog = Football(bot)
        await bot.add_cog(cog)
        logger.info("Football cog added successfully")
        
        # Log the commands that were added
        commands = [cmd.name for cmd in cog.get_app_commands()]
        logger.info(f"Football commands registered: {commands}")
        
    except Exception as e:
        logger.error(f"Failed to add Football cog: {e!r}")
        raise
