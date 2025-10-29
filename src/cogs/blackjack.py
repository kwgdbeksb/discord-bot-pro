import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from utils.embed import set_branded_footer


# Simple card and deck definitions
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def make_deck() -> List[Tuple[str, str]]:
    return [(r, s) for s in SUITS for r in RANKS]


def card_value(rank: str) -> int:
    if rank in {"J", "Q", "K"}:
        return 10
    if rank == "A":
        return 11  # will adjust for soft ace later
    return int(rank)


def hand_value(cards: List[Tuple[str, str]]) -> Tuple[int, bool]:
    # returns (value, is_blackjack)
    total = 0
    aces = 0
    for r, _ in cards:
        v = card_value(r)
        total += v
        if r == "A":
            aces += 1
    # Adjust aces to avoid bust
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    is_bj = len(cards) == 2 and total == 21
    return total, is_bj


def pretty_cards(cards: List[Tuple[str, str]]) -> str:
    return " ".join([f"`{r}{s}`" for r, s in cards]) if cards else "—"


class BlackjackSession:
    def __init__(self, player_id: int):
        self.player_id = player_id
        # Two decks for lower chances of card counting, shuffled
        self.deck = make_deck() + make_deck()
        random.shuffle(self.deck)
        # Hands
        self.player: List[Tuple[str, str]] = []
        self.dealer: List[Tuple[str, str]] = []
        self.finished: bool = False
        self.result: Optional[str] = None  # "win" | "lose" | "push"

    def draw(self) -> Tuple[str, str]:
        if not self.deck:
            # reinitialize deck to keep game going
            self.deck = make_deck() + make_deck()
            random.shuffle(self.deck)
        return self.deck.pop()

    def start(self):
        self.player = [self.draw(), self.draw()]
        self.dealer = [self.draw(), self.draw()]

    def hit(self, target: str = "player"):
        if target == "player":
            self.player.append(self.draw())
        else:
            self.dealer.append(self.draw())

    def dealer_play(self):
        # Dealer hits until 17 or more; treat soft 17 as stand
        while True:
            value, _ = hand_value(self.dealer)
            if value < 17:
                self.hit("dealer")
            else:
                break

    def settle(self):
        pv, pbj = hand_value(self.player)
        dv, dbj = hand_value(self.dealer)
        if pv > 21:
            self.result = "lose"
        elif dv > 21:
            self.result = "win"
        elif pbj and not dbj:
            self.result = "win"
        elif dbj and not pbj:
            self.result = "lose"
        elif pv > dv:
            self.result = "win"
        elif pv < dv:
            self.result = "lose"
        else:
            self.result = "push"
        self.finished = True


class BlackjackUI(discord.ui.View):
    def __init__(self, cog: "Blackjack", session: BlackjackSession, invoker: discord.Member, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session = session
        self.invoker = invoker
        self.message: Optional[discord.Message] = None

    async def _refresh(self, interaction: Optional[discord.Interaction] = None, final: bool = False):
        # Build embed
        player_val, player_bj = hand_value(self.session.player)
        dealer_val, dealer_bj = hand_value(self.session.dealer)
        hidden = not self.session.finished
        dealer_show = self.session.dealer if self.session.finished else ([self.session.dealer[0]] if self.session.dealer else [])

        title = "🃏 Blackjack"
        desc_lines = [
            f"**Player** ({self.invoker.mention}) — `{player_val}`{' • Blackjack!' if player_bj else ''}\n{pretty_cards(self.session.player)}",
            "",
            f"**Dealer** — `{dealer_val if self.session.finished else '?'}" + (" • Blackjack!" if dealer_bj and self.session.finished else "") + f"\n{pretty_cards(dealer_show)}",
        ]
        if self.session.finished and self.session.result:
            outcome_map = {"win": "✅ You win!", "lose": "❌ Dealer wins.", "push": "➖ Push."}
            desc_lines.append("")
            desc_lines.append(outcome_map.get(self.session.result, ""))

        color = discord.Color.green() if (self.session.finished and self.session.result == "win") else discord.Color.red() if (self.session.finished and self.session.result == "lose") else discord.Color.blurple()
        embed = discord.Embed(title=title, description="\n".join(desc_lines), color=color, timestamp=datetime.now(timezone.utc))
        try:
            embed.set_author(name=f"{self.invoker.display_name}", icon_url=self.invoker.display_avatar.url)
        except Exception:
            pass
        set_branded_footer(embed)

        # Buttons state
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = self.session.finished

        if interaction and interaction.response and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            if self.message:
                await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.player_id:
            return await interaction.response.send_message("This isn’t your game.", ephemeral=True)
        self.session.hit("player")
        pv, _ = hand_value(self.session.player)
        if pv > 21:
            # Bust; dealer settles
            self.session.dealer_play()
            self.session.settle()
            await self._refresh(interaction, final=True)
            return
        await self._refresh(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.player_id:
            return await interaction.response.send_message("This isn’t your game.", ephemeral=True)
        self.session.dealer_play()
        self.session.settle()
        await self._refresh(interaction, final=True)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success)
    async def double_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.player_id:
            return await interaction.response.send_message("This isn’t your game.", ephemeral=True)
        # Double: one final hit then stand
        self.session.hit("player")
        pv, _ = hand_value(self.session.player)
        if pv <= 21:
            self.session.dealer_play()
        self.session.settle()
        await self._refresh(interaction, final=True)


class Blackjack(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # sessions per guild and user
        self.sessions: dict[Tuple[int, int], BlackjackSession] = {}
        # multiplayer tables per guild and channel
        self.table_sessions: dict[Tuple[int, int], "BlackjackTableSession"] = {}

    def _key(self, guild_id: int, user_id: int) -> Tuple[int, int]:
        return (guild_id, user_id)

    def _make_session(self, guild_id: int, user_id: int) -> BlackjackSession:
        sess = BlackjackSession(player_id=user_id)
        sess.start()
        self.sessions[self._key(guild_id, user_id)] = sess
        return sess

    def _remove_session(self, guild_id: int, user_id: int):
        self.sessions.pop(self._key(guild_id, user_id), None)

    # User-install only to avoid duplicate entries in guilds; allow DMs and private channels
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.command(name="blackjack", description="Play a quick game of Blackjack against the dealer")
    async def blackjack(self, interaction: discord.Interaction):
        # Support both guild channels and DMs/group DMs for user installs.
        # Use a context-scoped key: guild.id for servers; channel.id for DMs/private channels.
        # In rare cases where channel is None, fall back to user.id to avoid failures.
        ctx_id = (
            interaction.guild.id if interaction.guild is not None else (
                getattr(interaction, "channel", None).id if getattr(interaction, "channel", None) is not None else interaction.user.id
            )
        )
        user_id = interaction.user.id
        existing = self.sessions.get(self._key(ctx_id, user_id))
        if existing and not existing.finished:
            # Reuse session
            sess = existing
        else:
            sess = self._make_session(ctx_id, user_id)

        view = BlackjackUI(cog=self, session=sess, invoker=interaction.user)
        player_val, player_bj = hand_value(sess.player)
        dealer_val, dealer_bj = hand_value(sess.dealer)
        title = "🃏 Blackjack"
        desc_lines = [
            f"**Player** ({interaction.user.mention}) — `{player_val}`{' • Blackjack!' if player_bj else ''}\n{pretty_cards(sess.player)}",
            "",
            f"**Dealer** — `?`\n{pretty_cards([sess.dealer[0]] if sess.dealer else [])}",
        ]
        embed = discord.Embed(title=title, description="\n".join(desc_lines), color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
        try:
            author_name = interaction.user.global_name or interaction.user.display_name
            embed.set_author(name=f"{author_name}", icon_url=interaction.user.display_avatar.url)
        except Exception:
            pass
        set_branded_footer(embed)

        await interaction.response.send_message(embed=embed, view=view)
        try:
            view.message = await interaction.original_response()
        except Exception:
            view.message = None

    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.command(name="blackjack_table", description="Create a multiplayer Blackjack table lobby in this channel")
    async def blackjack_table(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        key = (interaction.guild.id, interaction.channel.id)
        existing = self.table_sessions.get(key)
        if existing and not existing.finished:
            view = BlackjackTableLobby(self, existing, interaction.user)
            title = "🃏 Blackjack Table — Lobby"
            embed = discord.Embed(title=title, description="A table already exists in this channel.", color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
            set_branded_footer(embed)
            await interaction.response.send_message(embed=embed, view=view)
            try:
                view.message = await interaction.original_response()
            except Exception:
                view.message = None
            await view._refresh(None)
            return

        sess = BlackjackTableSession(interaction.guild.id, interaction.channel.id, interaction.user.id)
        self.table_sessions[key] = sess
        lobby = BlackjackTableLobby(self, sess, interaction.user)
        title = "🃏 Blackjack Table — Lobby"
        desc = [
            f"Host: {interaction.user.mention}",
            "",
            "Players:",
            "• None",
            "",
            "Press Join to sit. Host presses Start when ready.",
        ]
        embed = discord.Embed(title=title, description="\n".join(desc), color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
        try:
            embed.set_author(name=f"{interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        except Exception:
            pass
        set_branded_footer(embed)
        await interaction.response.send_message(embed=embed, view=lobby)
        try:
            lobby.message = await interaction.original_response()
        except Exception:
            lobby.message = None


async def setup(bot: commands.Bot):
    await bot.add_cog(Blackjack(bot))


# Multiplayer Blackjack (table)

class BlackjackTableSession:
    def __init__(self, guild_id: int, channel_id: int, host_id: int):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.host_id = host_id
        self.deck = make_deck() + make_deck()
        random.shuffle(self.deck)
        self.dealer: List[Tuple[str, str]] = []
        self.players: dict[int, List[Tuple[str, str]]] = {}
        self.order: List[int] = []
        self.turn_index: int = 0
        self.started: bool = False
        self.finished: bool = False
        self.results: dict[int, str] = {}

    def draw(self) -> Tuple[str, str]:
        if not self.deck:
            self.deck = make_deck() + make_deck()
            random.shuffle(self.deck)
        return self.deck.pop()

    def add_player(self, user_id: int) -> bool:
        if self.started or self.finished:
            return False
        if user_id in self.players:
            return False
        self.players[user_id] = []
        self.order.append(user_id)
        return True

    def remove_player(self, user_id: int) -> bool:
        if self.started or self.finished:
            return False
        if user_id not in self.players:
            return False
        self.players.pop(user_id, None)
        try:
            self.order.remove(user_id)
        except ValueError:
            pass
        return True

    def start(self) -> bool:
        if self.started or self.finished:
            return False
        if not self.order:
            return False
        self.started = True
        self.dealer = [self.draw(), self.draw()]
        for uid in self.order:
            self.players[uid] = [self.draw(), self.draw()]
        self.turn_index = 0
        return True

    def current_player_id(self) -> Optional[int]:
        if not self.started or self.finished:
            return None
        if self.turn_index < 0 or self.turn_index >= len(self.order):
            return None
        return self.order[self.turn_index]

    def advance_turn(self):
        if not self.started or self.finished:
            return
        self.turn_index += 1
        # Skip players who already busted (value > 21) or are None
        while self.turn_index < len(self.order):
            uid = self.order[self.turn_index]
            hand = self.players.get(uid, [])
            val, _ = hand_value(hand)
            if val > 21:
                self.turn_index += 1
                continue
            break
        if self.turn_index >= len(self.order):
            self.dealer_play()
            self.settle_all()

    def player_hit(self, user_id: int):
        if self.finished or not self.started:
            return
        cur = self.current_player_id()
        if cur != user_id:
            return
        self.players[user_id].append(self.draw())
        val, _ = hand_value(self.players[user_id])
        if val > 21:
            self.advance_turn()

    def player_stand(self, user_id: int):
        if self.finished or not self.started:
            return
        cur = self.current_player_id()
        if cur != user_id:
            return
        self.advance_turn()

    def player_double(self, user_id: int):
        if self.finished or not self.started:
            return
        cur = self.current_player_id()
        if cur != user_id:
            return
        self.players[user_id].append(self.draw())
        val, _ = hand_value(self.players[user_id])
        self.advance_turn()

    def dealer_play(self):
        while True:
            value, _ = hand_value(self.dealer)
            if value < 17:
                self.dealer.append(self.draw())
            else:
                break

    def settle_all(self):
        dv, dbj = hand_value(self.dealer)
        for uid, hand in self.players.items():
            pv, pbj = hand_value(hand)
            if pv > 21:
                self.results[uid] = "lose"
            elif dv > 21:
                self.results[uid] = "win"
            elif pbj and not dbj:
                self.results[uid] = "win"
            elif dbj and not pbj:
                self.results[uid] = "lose"
            elif pv > dv:
                self.results[uid] = "win"
            elif pv < dv:
                self.results[uid] = "lose"
            else:
                self.results[uid] = "push"
        self.finished = True


class BlackjackTableLobby(discord.ui.View):
    def __init__(self, cog: "Blackjack", session: BlackjackTableSession, host: discord.Member, timeout: Optional[float] = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session = session
        self.host = host
        self.message: Optional[discord.Message] = None

    async def _refresh(self, interaction: Optional[discord.Interaction] = None):
        guild = interaction.guild if interaction else None
        players_lines: List[str] = []
        if guild:
            for uid in self.session.order:
                member = guild.get_member(uid)
                if member:
                    players_lines.append(f"• {member.mention}")
                else:
                    players_lines.append(f"• <@{uid}>")
        else:
            players_lines = [f"• <@{uid}>" for uid in self.session.order]

        title = "🃏 Blackjack Table — Lobby"
        desc = [
            f"Host: {self.host.mention}",
            "",
            "Players:",
            *(players_lines if players_lines else ["• None"]),
            "",
            "Press Join to sit. Host presses Start when ready.",
        ]
        embed = discord.Embed(title=title, description="\n".join(desc), color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
        try:
            embed.set_author(name=f"{self.host.display_name}", icon_url=self.host.display_avatar.url)
        except Exception:
            pass
        set_branded_footer(embed)

        if interaction and interaction.response and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            if self.message:
                await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.finished:
            return await interaction.response.send_message("Table is finished.", ephemeral=True)
        ok = self.session.add_player(interaction.user.id)
        if not ok:
            return await interaction.response.send_message("You’re already seated or the game started.", ephemeral=True)
        await self._refresh(interaction)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.session.host_id:
            return await interaction.response.send_message("Host cannot leave. Use Cancel.", ephemeral=True)
        ok = self.session.remove_player(interaction.user.id)
        if not ok:
            return await interaction.response.send_message("You’re not seated or game started.", ephemeral=True)
        await self._refresh(interaction)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.host_id:
            return await interaction.response.send_message("Only the host can start.", ephemeral=True)
        if not self.session.start():
            return await interaction.response.send_message("Need at least one player to start.", ephemeral=True)
        game_view = BlackjackTableGame(self.cog, self.session, self.host)
        await game_view._refresh(interaction)
        game_view.message = self.message

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.session.host_id:
            return await interaction.response.send_message("Only the host can cancel.", ephemeral=True)
        self.session.finished = True
        await interaction.response.edit_message(content="Table canceled.", embed=None, view=None)
        key = (interaction.guild.id, interaction.channel.id) if interaction.guild else None
        if key:
            self.cog.table_sessions.pop(key, None)


class BlackjackTableGame(discord.ui.View):
    def __init__(self, cog: "Blackjack", session: BlackjackTableSession, host: discord.Member, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session = session
        self.host = host
        self.message: Optional[discord.Message] = None

    async def _refresh(self, interaction: Optional[discord.Interaction] = None, final: bool = False):
        guild = interaction.guild if interaction else None
        title = "🃏 Blackjack Table"
        lines: List[str] = []
        cur = self.session.current_player_id()
        for uid in self.session.order:
            member_name = f"<@{uid}>"
            if guild:
                m = guild.get_member(uid)
                if m:
                    member_name = m.mention
            hand = self.session.players.get(uid, [])
            val, bj = hand_value(hand)
            marker = " • Your turn" if cur == uid and not self.session.finished else ""
            lines.append(f"**Player** ({member_name}) — `{val}`{' • Blackjack!' if bj else ''}{marker}\n{pretty_cards(hand)}")
            lines.append("")

        dv, dbj = hand_value(self.session.dealer)
        dealer_show = self.session.dealer if self.session.finished else ([self.session.dealer[0]] if self.session.dealer else [])
        lines.append(f"**Dealer** — `{dv if self.session.finished else '?'}" + (" • Blackjack!" if dbj and self.session.finished else "") + f"\n{pretty_cards(dealer_show)}")

        if self.session.finished:
            lines.append("")
            res_map = {"win": "✅ Win", "lose": "❌ Lose", "push": "➖ Push"}
            summary = [
                f"{(guild.get_member(uid).mention if guild and guild.get_member(uid) else f'<@{uid}>')} — {res_map.get(self.session.results.get(uid, ''), '')}"
                for uid in self.session.order
            ]
            lines.extend(summary)

        color = discord.Color.green() if self.session.finished else discord.Color.blurple()
        embed = discord.Embed(title=title, description="\n".join(lines), color=color, timestamp=datetime.now(timezone.utc))
        try:
            embed.set_author(name=f"{self.host.display_name}", icon_url=self.host.display_avatar.url)
        except Exception:
            pass
        set_branded_footer(embed)

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = self.session.finished or (self.session.current_player_id() is None)

        if interaction and interaction.response and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            if self.message:
                await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.finished:
            return await interaction.response.send_message("Game finished.", ephemeral=True)
        if interaction.user.id != self.session.current_player_id():
            return await interaction.response.send_message("Not your turn.", ephemeral=True)
        self.session.player_hit(interaction.user.id)
        await self._refresh(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.finished:
            return await interaction.response.send_message("Game finished.", ephemeral=True)
        if interaction.user.id != self.session.current_player_id():
            return await interaction.response.send_message("Not your turn.", ephemeral=True)
        self.session.player_stand(interaction.user.id)
        await self._refresh(interaction)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success)
    async def double_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.finished:
            return await interaction.response.send_message("Game finished.", ephemeral=True)
        if interaction.user.id != self.session.current_player_id():
            return await interaction.response.send_message("Not your turn.", ephemeral=True)
        self.session.player_double(interaction.user.id)
        await self._refresh(interaction)
