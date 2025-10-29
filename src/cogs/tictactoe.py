import discord
from utils.embed import set_branded_footer
import time
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands


class TicTacToeButton(discord.ui.Button["TicTacToeView"]):
    def __init__(self, x: int, y: int):
        # Use zero-width space to satisfy Discord's required label without visual clutter
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y
        # Initial emoji for empty cells
        self.emoji = "▫️"

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        assert isinstance(view, TicTacToeView)

        if view.current_player_id != interaction.user.id:
            # Ephemeral is not supported in DMs; only use ephemeral in guilds
            is_dm = interaction.guild is None
            ephemeral_ok = not is_dm
            await interaction.response.send_message("It's not your turn.", ephemeral=ephemeral_ok)
            return

        if view.board[self.y][self.x] != 0:
            is_dm = interaction.guild is None
            ephemeral_ok = not is_dm
            await interaction.response.send_message("This spot is already taken.", ephemeral=ephemeral_ok)
            return

        mark = 1 if view.current_player == "X" else -1
        view.board[self.y][self.x] = mark
        view.last_move = (self.x, self.y)
        view.move_count += 1
        self.label = view.current_player
        self.style = (
            discord.ButtonStyle.success if view.current_player == "X" else discord.ButtonStyle.danger
        )
        self.emoji = "❌" if view.current_player == "X" else "⭕"
        self.disabled = True

        # Record move in history
        view.moves.append((view.current_player, view.cell_name(self.x, self.y)))

        winner = view.check_winner()
        if winner is not None:
            status = "It's a tie!" if winner == 0 else f"{view.current_player} wins!"
            view.winning_cells = view.get_winning_cells() if winner != 0 else None
            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(embed=view.make_embed(status, final=True), view=view)
            view.stop()
        else:
            view.toggle_player()
            await interaction.response.edit_message(embed=view.make_embed(f"{view.current_player}'s turn"), view=view)


class TicTacToeView(discord.ui.View):
    def __init__(self, player_x: discord.User, player_o: discord.User, timeout: int = 1800):
        super().__init__(timeout=timeout)
        self.board = [[0] * 3 for _ in range(3)]
        self.current_player = "X"
        self.player_x_user = player_x
        self.player_o_user = player_o
        self.player_x_id = player_x.id
        self.player_o_id = player_o.id
        self.current_player_id = self.player_x_id
        self.header = f"X: <@{self.player_x_id}> | O: <@{self.player_o_id}>"
        self.message: discord.Message | None = None
        self.move_count: int = 0
        self.last_move: tuple[int, int] | None = None  # (x, y)
        self.moves: list[tuple[str, str]] = []  # (mark, cell)
        self.start_time: datetime = datetime.now(timezone.utc)
        self.timeout_seconds: int = timeout
        self.winning_cells: list[tuple[int, int]] | None = None

        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def cell_name(self, x: int, y: int) -> str:
        return f"{'ABC'[x]}{'123'[y]}"

    def render_board(self) -> str:
        symbols = {1: "❌", -1: "⭕", 0: "▫️"}
        lines: list[str] = []
        lines.append("   A  B  C")
        for y, row in enumerate(self.board):
            row_symbols: list[str] = []
            for x, cell in enumerate(row):
                s = symbols[cell]
                # Winning cells take precedence in highlight, then last move
                if self.winning_cells and (x, y) in self.winning_cells:
                    s = f"〔{s}〕"
                elif self.last_move and (x, y) == self.last_move:
                    s = f"【{s}】"
                row_symbols.append(s)
            lines.append(f"{y+1}  " + " ".join(row_symbols))
        return "\n".join(lines)

    def get_winning_cells(self) -> list[tuple[int, int]] | None:
        b = self.board
        # Rows
        for y in range(3):
            s = sum(b[y])
            if abs(s) == 3:
                return [(x, y) for x in range(3)]
        # Columns
        for x in range(3):
            s = b[0][x] + b[1][x] + b[2][x]
            if abs(s) == 3:
                return [(x, y) for y in range(3)]
        # Diagonals
        if abs(b[0][0] + b[1][1] + b[2][2]) == 3:
            return [(0, 0), (1, 1), (2, 2)]
        if abs(b[0][2] + b[1][1] + b[2][0]) == 3:
            return [(2, 0), (1, 1), (0, 2)]
        return None

    def check_winner(self) -> int | None:
        lines = []
        # Rows and columns
        for i in range(3):
            lines.append(sum(self.board[i]))
            lines.append(self.board[0][i] + self.board[1][i] + self.board[2][i])
        # Diagonals
        lines.append(self.board[0][0] + self.board[1][1] + self.board[2][2])
        lines.append(self.board[0][2] + self.board[1][1] + self.board[2][0])

        if 3 in lines:
            return 1
        if -3 in lines:
            return -1
        if all(self.board[y][x] != 0 for y in range(3) for x in range(3)):
            return 0
        return None

    def toggle_player(self):
        if self.current_player == "X":
            self.current_player = "O"
            self.current_player_id = self.player_o_id
        else:
            self.current_player = "X"
            self.current_player_id = self.player_x_id

    def current_user(self) -> discord.User:
        return self.player_x_user if self.current_player == "X" else self.player_o_user

    def make_embed(self, status: str, final: bool = False, timeout_msg: bool = False) -> discord.Embed:
        # Color logic: timeout -> blurple, tie -> orange, else X green / O red
        if timeout_msg:
            color = discord.Color.blurple()
        elif final and ("tie" in status.lower()):
            color = discord.Color.orange()
        else:
            color = discord.Color.green() if self.current_player == "X" else discord.Color.red()

        title = "TicTacToe Match"
        embed = discord.Embed(title=title, description=status, color=color)
        set_branded_footer(embed)

        # Author avatar reflects the active player (or last mover at game end)
        user = self.current_user()
        try:
            embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        except Exception:
            embed.set_author(name=user.display_name)

        # Players field
        players_value = f"❌ <@{self.player_x_id}>\n⭕ <@{self.player_o_id}>"
        embed.add_field(name="Players", value=players_value, inline=True)

        # Turn / Result field
        if not final and not timeout_msg:
            turn_emoji = "❌" if self.current_player == "X" else "⭕"
            embed.add_field(name="Turn", value=f"{turn_emoji} {user.mention}", inline=True)
        elif final:
            if "wins" in status.lower():
                win_emoji = "❌" if self.current_player == "X" else "⭕"
                embed.add_field(name="Winner", value=f"{win_emoji} {user.mention}", inline=True)
            else:
                embed.add_field(name="Result", value="🤝 Tie", inline=True)

        # Moves counter
        embed.add_field(name="Moves", value=str(self.move_count), inline=True)

        # Last move indicator
        if self.last_move is not None:
            lx, ly = self.last_move
            # At final, current_player is the winner/last mover; during turns, last mover is the opposite
            last_mover_mark = "X" if final else ("O" if self.current_player == "X" else "X")
            mover_emoji = "❌" if last_mover_mark == "X" else "⭕"
            last_cell = self.cell_name(lx, ly)
            embed.add_field(name="Last Move", value=f"{mover_emoji} {last_cell}", inline=True)

        # History (show up to 6 recent moves, more when final)
        if self.moves:
            show_count = 9 if final else 6
            recent = self.moves[-show_count:]
            hist = " → ".join(f"{'❌' if m=='X' else '⭕'} {c}" for m, c in recent)
            embed.add_field(name="History", value=hist, inline=False)

        # Board grid (monospaced for alignment)
        board_block = f"```\n{self.render_board()}\n```"
        embed.add_field(name="Board", value=board_block, inline=False)

        # Timeline: started and expiry
        started_ts = int(self.start_time.timestamp())
        expires_ts = int(self.start_time.timestamp()) + self.timeout_seconds
        timeline = f"Started: <t:{started_ts}:R>\nExpires: <t:{expires_ts}:R>"
        embed.add_field(name="Timeline", value=timeline, inline=True)

        # Controls hint
        controls = "Tap a cell button to place your mark.\nCoords: A–C and 1–3."
        embed.add_field(name="Controls", value=controls, inline=True)

        set_branded_footer(embed)
        return embed

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embed=self.make_embed("Game timed out.", timeout_msg=True), view=self)
            except Exception:
                pass
        self.stop()


class TicTacToe(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name="tictactoe", description="Start a TicTacToe game with another user")
    @app_commands.describe(opponent="The user to play against", minutes="Game timeout in minutes (1-60)")
    async def tictactoe(self, interaction: discord.Interaction, opponent: discord.User, minutes: int | None = None):
        if opponent.bot:
            is_dm = interaction.guild is None
            ephemeral_ok = not is_dm
            await interaction.response.send_message("You cannot play against a bot.", ephemeral=ephemeral_ok)
            return
        if opponent.id == interaction.user.id:
            ephemeral_ok = not is_dm
            await interaction.response.send_message("You cannot play against yourself.", ephemeral=ephemeral_ok)
            return

        # Determine timeout in seconds (default 30 minutes). Clamp to 1-60 minutes.
        if minutes is None:
            timeout = 30 * 60
        else:
            timeout = max(1, min(60, minutes)) * 60

        view = TicTacToeView(player_x=interaction.user, player_o=opponent, timeout=timeout)
        await interaction.response.send_message(embed=view.make_embed(f"{view.current_player}'s turn"), view=view)
        try:
            view.message = await interaction.original_response()
        except Exception:
            view.message = None


async def setup(bot: commands.Bot):
    await bot.add_cog(TicTacToe(bot))
