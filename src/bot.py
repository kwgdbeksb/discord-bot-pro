import asyncio
import os
from datetime import datetime, timezone
from collections import deque
import discord
from discord.ext import commands
from discord import app_commands

from config import load_config
from utils.logger import setup_logger
import wavelink


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # allow reading messages in group chats
        config = load_config()
        super().__init__(
            command_prefix=commands.when_mentioned_or("!", ">"),
            intents=intents,
            application_id=config.app_id,
            status=discord.Status.dnd,
            activity=discord.Activity(type=discord.ActivityType.watching, name="you from the shadows"),
        )
        self.logger = setup_logger()
        self.config = config
        self.owner_id = self.config.owner_id
        # Track last-set presence for accurate confirmations
        self.presence_status: discord.Status = discord.Status.dnd
        self.presence_activity: discord.BaseActivity | None = discord.Activity(
            type=discord.ActivityType.watching, name="you from the shadows"
        )
        # Track bot start time for uptime metrics
        self.start_time: datetime = datetime.now(timezone.utc)
        # Internal flag to avoid duplicate per-guild syncs
        self._synced_per_guild: bool = False
        # Owner DM notifications
        self._owner_dm_task: asyncio.Task | None = None
        self._startup_dm_sent: bool = False
        # DM relay: track target user IDs whose DMs should be forwarded to owner
        self.dm_relay_targets: set[int] = set()
        # In-memory audit log entries (rolling buffer)
        self.audit_log_entries: deque[dict] = deque(maxlen=2000)

    async def setup_hook(self):
        """Setup hook called when the bot is starting up."""
        self.logger.info("🚀 Starting bot setup hook...")
        
        # Initialize Wavelink nodes
        self.logger.info("🔧 Initializing Wavelink...")
        nodes = [wavelink.Node(uri=f"http://{self.config.lavalink_host}:{self.config.lavalink_port}", password=self.config.lavalink_password)]
        await wavelink.Pool.connect(nodes=nodes, client=self)
        
        # Load cogs
        self.logger.info("📦 Loading cogs...")
        
        # Load general cog
        self.logger.info("📦 Loading general cog...")
        try:
            await self.load_extension("cogs.general")
            self.logger.info("✅ Loaded general cog.")
        except Exception as e:
            self.logger.error(f"❌ Failed to load general cog: {e!r}")

        # Load tictactoe cog
        self.logger.info("📦 Loading tictactoe cog...")
        try:
            await self.load_extension("cogs.tictactoe")
            self.logger.info("✅ Loaded tictactoe cog.")
        except Exception as e:
            self.logger.error(f"❌ Failed to load tictactoe cog: {e!r}")

        # Load blackjack cog
        self.logger.info("📦 Loading blackjack cog...")
        try:
            await self.load_extension("cogs.blackjack")
            self.logger.info("✅ Loaded blackjack cog.")
        except Exception as e:
            self.logger.error(f"❌ Failed to load blackjack cog: {e!r}")

        # Load football cog
        self.logger.info("📦 Loading football cog...")
        try:
            await self.load_extension("cogs.football")
            self.logger.info("✅ Loaded football cog.")
        except Exception as e:
            self.logger.error(f"❌ Failed to load football cog: {e!r}")

        # Load the music cog with Wavelink functionality
        self.logger.info("📦 Loading music cog...")
        try:
            await self.load_extension("cogs.music")
            self.logger.info("✅ Loaded music cog.")
        except Exception as e:
            self.logger.error(f"❌ Failed to load music cog: {e!r}")

        # Load Jishaku for diagnostics as text commands only; restrict to guilds
        self.logger.info("📦 Loading Jishaku extension...")
        try:
            # Prevent Jishaku from using slash commands and set default prefix
            os.environ.setdefault("JISHAKU_NO_UNDERSCORE", "true")
            os.environ.setdefault("JISHAKU_NO_DM_TRACEBACK", "true")
            await self.load_extension("jishaku")
            self.logger.info("✅ Loaded Jishaku extension.")
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to load Jishaku: {e!r}")

        # Start Wavelink health check task
        self.logger.info("🏥 Starting Wavelink health check task...")
        self.loop.create_task(self._wavelink_health_check())
        self.logger.info("✅ Wavelink health check task started")

        # Sync commands after all cogs are loaded
        self.logger.info("🔄 Syncing commands...")
        try:
            if self.config.sync_global:
                self.logger.info("🌍 Syncing global commands...")
                synced = await self.tree.sync()
                self.logger.info(f"✅ Synced {len(synced)} global commands")
            else:
                self.logger.info("🚫 Global sync disabled in config")
        except Exception as e:
            self.logger.error(f"❌ Failed to sync commands: {e!r}")
        
        # Log all registered commands for debugging
        self.logger.info("📋 Getting command list...")
        try:
            all_commands = self.tree.get_commands()
            command_names = [cmd.name for cmd in all_commands]
            self.logger.info(f"📋 All registered commands: {command_names}")
        except Exception as e:
            self.logger.error(f"❌ Failed to get command list: {e!r}")
            
        self.logger.info("🎉 Setup hook completed successfully!")

    async def _wavelink_health_check(self):
        """Periodic health check for Wavelink nodes."""
        await asyncio.sleep(30)  # Wait for initial startup
        
        while not self.is_closed():
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Check if we have any connected nodes
                nodes = wavelink.Pool.nodes
                healthy_nodes = []
                
                for node in nodes.values():
                    try:
                        if node.status == wavelink.NodeStatus.CONNECTED:
                            healthy_nodes.append(node)
                    except Exception:
                        continue
                
                if not healthy_nodes:
                    self.logger.warning("No healthy Wavelink nodes found.")
                else:
                    # Log healthy status periodically (every 10 minutes)
                    if hasattr(self, '_last_health_log'):
                        if (asyncio.get_event_loop().time() - self._last_health_log) > 600:
                            self.logger.info(f"Wavelink health check: {len(healthy_nodes)} healthy node(s)")
                            self._last_health_log = asyncio.get_event_loop().time()
                    else:
                        self._last_health_log = asyncio.get_event_loop().time()
                        
            except Exception as e:
                self.logger.error(f"Error in Wavelink health check: {e!r}")
                await asyncio.sleep(30)  # Wait longer on error

    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        """Handle Wavelink node ready events."""
        try:
            self.logger.info(f"Wavelink node '{payload.node.identifier}' is ready!")
        except Exception:
            pass

        # Sync strategy:
        # - If sync_global is True: sync globally and keep commands available in DMs (User Install).
        # - If a dev guild is configured and sync_global is False: sync to that guild and PRESERVE global
        #   commands so user-install commands (like /minesmulti in DMs) still work.
        # - If neither is set and sync_global is False: defer per-guild sync on ready, also PRESERVING
        #   global commands to keep DM availability.
        if self.config.sync_global:
            self.logger.info("Syncing commands globally (avoiding guild duplicates)...")
            await self.tree.sync()
            # Prevent on_ready from performing per-guild sync
            self._synced_per_guild = True
        elif self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.logger.info(
                f"Syncing commands to dev guild {guild.id} and preserving global for user installs..."
            )
            # Ensure global commands exist so user-install and DM contexts have access
            try:
                await self.tree.sync()
            except Exception as e:
                self.logger.warning(f"Global sync failed during dev guild sync path: {e!r}")
            # Also sync to the dev guild for instant updates while developing
            await self.tree.sync(guild=guild)
        else:
            # Default to deferring per-guild sync; keep global commands for DM/user-install contexts
            self.logger.info("Global sync deferred; will sync per-guild on ready (global preserved for DMs).")

        # Start hourly owner stats DM loop
        try:
            if not self._owner_dm_task:
                self._owner_dm_task = asyncio.create_task(self._owner_dm_loop())
                self.logger.info("Initialized hourly owner stats DM task.")
        except Exception as e:
            try:
                self.logger.warning(f"Failed to start hourly owner DM task: {e!r}")
            except Exception:
                pass

    async def on_ready(self):
        self.logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        self.logger.info("Bot is ready.")
        
        # Set bot presence: DND status with a Watching activity
        try:
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="you from the shadows"
                ),
            )
            try:
                self.presence_status = discord.Status.dnd
                self.presence_activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name="you from the shadows"
                )
            except Exception:
                pass
        except Exception as e:
            try:
                self.logger.warning(f"Failed to set presence: {e!r}")
            except Exception:
                pass
        # No-op: guild-only restriction for Jishaku applied via global check in setup
        # If global sync is enabled, ensure no guild-scoped duplicates remain
        if self.config.sync_global:
            try:
                guilds = list(self.guilds)
                if guilds:
                    self.logger.info("Cleaning up guild-scoped duplicates (keeping global commands only)...")
                    cleaned = 0
                    for g in guilds:
                        obj = discord.Object(id=g.id)
                        # Clear guild commands and sync an empty set for that guild
                        self.tree.clear_commands(guild=obj)
                        await self.tree.sync(guild=obj)
                        cleaned += 1
                    self.logger.info(f"Cleaned guild-scoped commands in {cleaned} guild(s).")
            except Exception as e:
                self.logger.warning(f"Guild command cleanup failed: {e!r}")
            # Do not perform per-guild sync when global is active
            # Attempt optional auto-play before returning
            await self._attempt_auto_play()
            # Send startup DM once
            try:
                if not self._startup_dm_sent:
                    await self._send_owner_stats_dm(
                        title="✅ Bot Online",
                        extra_note="Startup notification; hourly reports will continue automatically.",
                    )
                    self._startup_dm_sent = True
                
            except Exception as e:
                try:
                    self.logger.warning(f"Failed to send startup owner DM: {e!r}")
                except Exception:
                    pass
            self._synced_per_guild = True
            return

        # If no single dev guild is configured and we haven't synced per-guild yet, do it now
        if not self.config.guild_id and not self._synced_per_guild:
            try:
                guilds = list(self.guilds)
                if guilds:
                    # Sync per-guild for fast iteration without copying global to avoid duplicates
                    self.logger.info(f"Syncing commands to {len(guilds)} joined guild(s) (no global copy to avoid duplicates)...")
                    synced_count = 0
                    for g in guilds:
                        obj = discord.Object(id=g.id)
                        await self.tree.sync(guild=obj)
                        synced_count += 1
                    self.logger.info(f"Synced commands to {synced_count} guild(s).")
                self._synced_per_guild = True
            except Exception as e:
                self.logger.warning(f"Failed to sync commands to joined guilds: {e!r}")

        # If a dev guild is configured and global sync is disabled, ensure ALL joined guilds get updated commands
        if self.config.guild_id and not self.config.sync_global and not self._synced_per_guild:
            try:
                guilds = list(self.guilds)
                if guilds:
                    self.logger.info(f"Dev-guild mode: syncing commands to {len(guilds)} joined guild(s) for immediate availability...")
                    synced_count = 0
                    for g in guilds:
                        obj = discord.Object(id=g.id)
                        await self.tree.sync(guild=obj)
                        synced_count += 1
                    self.logger.info(f"Synced commands to {synced_count} guild(s) in dev-guild mode.")
                self._synced_per_guild = True
            except Exception as e:
                self.logger.warning(f"Dev-guild per-guild sync failed: {e!r}")
        # Attempt optional auto-play after syncing
        await self._attempt_auto_play()

        # Send startup DM once
        try:
            if not self._startup_dm_sent:
                await self._send_owner_stats_dm(
                    title="✅ Bot Online",
                    extra_note="Startup notification; hourly reports will continue automatically.",
                )
                self._startup_dm_sent = True
        except Exception as e:
            try:
                self.logger.warning(f"Failed to send startup owner DM: {e!r}")
            except Exception:
                pass

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Log detailed info about command errors to help diagnose warnings/non-responses
        try:
            cmd_name = interaction.command.name if interaction and interaction.command else "unknown"
        except Exception:
            cmd_name = "unknown"
        self.logger.warning(f"App command error in '{cmd_name}': {error!r}")
        # Record errored slash command in audit log
        try:
            entry = self._build_audit_entry(
                interaction=interaction,
                command=getattr(interaction, "command", None),
                status="error",
                error=str(error),
            )
            if entry:
                self.audit_log_entries.append(entry)
        except Exception:
            pass
        # Attempt a graceful user-facing message if response not yet sent
        try:
            # Ephemeral messages are not supported in DMs; only use ephemeral in guilds
            is_dm = interaction.guild is None
            ephemeral_ok = not is_dm
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred while running this command.", ephemeral=ephemeral_ok)
            else:
                await interaction.followup.send("An error occurred while running this command.", ephemeral=ephemeral_ok)
        except Exception:
            # swallow follow-up failures; logging above suffices
            pass

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Provide a friendly message when non-owner attempts Jishaku commands
        try:
            if isinstance(error, commands.CheckFailure):
                cmd = getattr(ctx, "command", None)
                name = (getattr(cmd, "qualified_name", None) or getattr(cmd, "name", None) or "")
                if name.startswith("jsk"):
                    try:
                        await ctx.reply("Jishaku is restricted to the bot owner.", mention_author=False)
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        # Record errored prefix command in audit log
        try:
            entry = self._build_audit_entry(ctx=ctx, status="error", error=str(error))
            if entry:
                self.audit_log_entries.append(entry)
        except Exception:
            pass
        # Log other command errors
        try:
            cname = getattr(getattr(ctx, "command", None), "qualified_name", None) or "unknown"
            self.logger.warning(f"Command error in '{cname}': {error!r}")
        except Exception:
            pass

    async def _attempt_auto_play(self):
        """Optionally connect to a voice channel and play a test track on startup.

        Controlled via environment variables:
        - AUTO_PLAY_ON_STARTUP: enable (true/1/yes)
        - AUTO_PLAY_VOICE_CHANNEL_ID or AUTO_PLAY_CHANNEL_ID: target voice channel id
        - AUTO_PLAY_QUERY: URL or search query (defaults to 'ytsearch:never gonna give you up')
        """
        try:
            flag = os.getenv("AUTO_PLAY_ON_STARTUP", "false").lower() in {"1", "true", "yes"}
            if not flag:
                return
            self.logger.info("Auto-play on startup enabled; attempting to connect and play.")

            ch_id_env = os.getenv("AUTO_PLAY_VOICE_CHANNEL_ID") or os.getenv("AUTO_PLAY_CHANNEL_ID")
            channel = None
            if ch_id_env and ch_id_env.isdigit():
                ch_id = int(ch_id_env)
                channel = self.get_channel(ch_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(ch_id)
                    except Exception:
                        channel = None

            # Fallback: pick first joinable voice channel in joined guilds
            if channel is None or not isinstance(channel, discord.VoiceChannel):
                for g in self.guilds:
                    me = g.me
                    for ch in g.channels:
                        if isinstance(ch, discord.VoiceChannel):
                            try:
                                perms = ch.permissions_for(me)
                            except Exception:
                                perms = None
                            if perms and getattr(perms, "connect", False) and getattr(perms, "speak", False):
                                channel = ch
                                break
                    if isinstance(channel, discord.VoiceChannel):
                        break

            if channel is None or not isinstance(channel, discord.VoiceChannel):
                self.logger.warning("Auto-play: No joinable voice channel found; skipping.")
                return

            # Connect using Mafic player
            voice = channel.guild.voice_client
            try:
                connected = bool(voice and voice.is_connected())
            except Exception:
                connected = False
            if not connected:
                try:
                    await channel.connect(cls=mafic.Player)
                except Exception as e:
                    self.logger.warning(f"Auto-play: Failed to connect to channel '{channel.name}': {e!r}")
                    return

            player = channel.guild.voice_client
            if not isinstance(player, mafic.Player):
                # Ensure Mafic player
                try:
                    await channel.disconnect()
                except Exception:
                    pass
                try:
                    await channel.connect(cls=mafic.Player)
                    player = channel.guild.voice_client
                except Exception as e:
                    self.logger.warning(f"Auto-play: Failed to establish Mafic player: {e!r}")
                    return

            # Resolve track
            query = os.getenv("AUTO_PLAY_QUERY") or "ytsearch:never gonna give you up"

            def is_url(s: str) -> bool:
                s = s.strip()
                return s.startswith("http://") or s.startswith("https://") or "://" in s

            q = query.strip() if is_url(query) else (
                query if query.strip().lower().startswith("ytsearch:") else f"ytsearch:{query.strip()}"
            )
            try:
                # Get a node from the node pool for track searching
                if not hasattr(self.node_pool, '_nodes') or not self.node_pool._nodes:
                    self.logger.warning("Auto-play: No nodes available in the node pool")
                    return
                
                # Get the first available node
                node = next(iter(self.node_pool._nodes.values()))
                tracks = await node.get_tracks(q)
            except Exception as e:
                self.logger.warning(f"Auto-play: Search failed for query '{q}': {e!r}")
                return
            if not tracks:
                self.logger.warning(f"Auto-play: No tracks found for query '{q}'.")
                return
            track = tracks[0]

            # Prefer queueing via cog if available
            cog = self.get_cog("MusicMafic")
            if cog and hasattr(cog, "get_queue") and hasattr(cog, "start_player"):
                try:
                    queue = cog.get_queue(channel.guild.id)
                    await queue.put(track)
                    cog.start_player(channel.guild)
                    self.logger.info(
                        f"Auto-play: Queued and started '{getattr(track, 'title', 'Unknown')}' in '{channel.name}'."
                    )
                    return
                except Exception as e:
                    self.logger.warning(f"Auto-play: Failed to queue via cog; falling back to direct play: {e!r}")
            try:
                await player.play(track)
                self.logger.info(
                    f"Auto-play: Playing '{getattr(track, 'title', 'Unknown')}' in '{channel.name}'."
                )
            except Exception as e:
                self.logger.warning(f"Auto-play: Failed to play track: {e!r}")
        except Exception as e:
            try:
                self.logger.exception(f"Auto-play failed with unexpected error: {e!r}")
            except Exception:
                self.logger.warning(f"Auto-play failed with unexpected error: {e!r}")

    async def on_message(self, message: discord.Message):
        # Provide a friendly response for bare Jishaku invocation in DMs, and ensure commands are processed
        try:
            if message.author.bot:
                return
            # If in DMs and user types just '>jsk' or '!jsk', reply with guidance
            if message.guild is None:
                content = (message.content or "").strip()
                lowered = content.lower()
                if lowered in {">jsk", "!jsk"}:
                    await message.channel.send(
                        "Jishaku is ready here. Try `>jsk help`, `>jsk ping`, or `>jsk debug`."
                    )
                    return
                # Forward DM replies from relay targets to the bot owner
                try:
                    uid = int(message.author.id)
                    is_owner = self.owner_id is not None and uid == int(self.owner_id)
                except Exception:
                    uid = 0
                    is_owner = False
                if not is_owner and uid and uid in getattr(self, "dm_relay_targets", set()):
                    # Resolve owner
                    owner_user: discord.User | None = None
                    try:
                        owner_user = self.get_user(int(self.owner_id)) if self.owner_id else None
                    except Exception:
                        owner_user = None
                    if owner_user is None and self.owner_id:
                        try:
                            owner_user = await self.fetch_user(int(self.owner_id))
                        except Exception:
                            owner_user = None
                    if owner_user:
                        # Build forward embed
                        try:
                            embed = discord.Embed(
                                title="📥 DM Reply Received",
                                description=(message.content or "(no text)"),
                                color=discord.Color.blurple(),
                                timestamp=datetime.now(timezone.utc),
                            )
                            try:
                                embed.set_author(name=str(message.author), icon_url=getattr(message.author.display_avatar, "url", discord.Embed.Empty))
                            except Exception:
                                pass
                            # Include a hint for replying back
                            hint = f"Use `/reply user_id:{uid} message:<text>` to respond." if uid else "Use /reply to respond."
                            embed.add_field(name="How to respond", value=hint, inline=False)
                        except Exception:
                            embed = None
                        # Attachments: include URLs in a field
                        try:
                            attachments = message.attachments or []
                            if attachments:
                                urls = "\n".join([a.url for a in attachments if getattr(a, "url", None)])
                                if embed:
                                    embed.add_field(name="Attachments", value=urls[:1000], inline=False)
                        except Exception:
                            pass
                        # Send to owner
                        try:
                            if embed:
                                await owner_user.send(embed=embed)
                            else:
                                await owner_user.send(f"DM reply from {message.author} (ID: {uid}):\n{message.content}")
                        except Exception:
                            # Swallow forwarding failures
                            pass
            else:
                # In guild channels, respond to bare '>jsk' or '!jsk' too, respecting owner-only policy
                content = (message.content or "").strip()
                lowered = content.lower()
                if lowered in {">jsk", "!jsk"}:
                    try:
                        is_owner = self.owner_id is not None and int(message.author.id) == int(self.owner_id)
                    except Exception:
                        is_owner = False
                    if is_owner:
                        await message.reply(
                            "Jishaku is ready here. Try `>jsk help`, `>jsk ping`, or `>jsk debug`.",
                            mention_author=False,
                        )
                    else:
                        await message.reply("Jishaku is restricted to the bot owner.", mention_author=False)
                    return
        except Exception:
            # Swallow any DM guidance errors and continue to normal command processing
            pass
        # Let discord.py process prefix commands (including Jishaku)
        await self.process_commands(message)

    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command):
        """Record successful slash command invocations for audit logging."""
        try:
            entry = self._build_audit_entry(interaction=interaction, command=command, status="ok")
            if entry:
                self.audit_log_entries.append(entry)
        except Exception:
            pass

    async def on_interaction(self, interaction: discord.Interaction):
        """Log all interactions including button clicks, select menus, etc."""
        try:
            # Only log component interactions (buttons, selects, etc.), not slash commands
            if interaction.type == discord.InteractionType.component:
                entry = self._build_button_audit_entry(interaction)
                if entry:
                    self.audit_log_entries.append(entry)
        except Exception:
            pass

    async def on_command_completion(self, ctx: commands.Context):
        """Record successful prefix command invocations for audit logging."""
        try:
            entry = self._build_audit_entry(ctx=ctx, status="ok")
            if entry:
                self.audit_log_entries.append(entry)
        except Exception:
            pass

    def _format_interaction_options(self, options: object) -> str | None:
        """Format interaction options list into a compact string."""
        try:
            if not isinstance(options, list) or not options:
                return None
            parts: list[str] = []
            for opt in options:
                try:
                    name = str((opt or {}).get("name") or "")
                    typ = (opt or {}).get("type")
                    if typ in (1, 2):  # subcommand or group
                        sub = name
                        sub_opts = self._format_interaction_options((opt or {}).get("options"))
                        parts.append(sub if not sub_opts else f"{sub} {sub_opts}")
                    else:
                        val = (opt or {}).get("value")
                        v = str(val)
                        if len(v) > 60:
                            v = v[:59] + "…"
                        parts.append(f"{name}={v}")
                except Exception:
                    continue
            return " ".join(parts) if parts else None
        except Exception:
            return None

    def _build_button_audit_entry(self, interaction: discord.Interaction) -> dict | None:
        """Create an audit entry for button/component interactions."""
        try:
            now = datetime.now(timezone.utc)
            
            # Safe extraction of user data
            user = getattr(interaction, "user", None)
            user_id = None
            user_tag = None
            if user:
                try:
                    user_id = int(user.id)
                    user_tag = str(user)
                except Exception:
                    pass
            
            # Safe extraction of guild data
            guild = getattr(interaction, "guild", None)
            guild_id = None
            guild_name = None
            if guild:
                try:
                    guild_id = int(guild.id)
                    guild_name = str(guild.name)
                except Exception:
                    pass
            
            # Safe extraction of channel data
            channel = getattr(interaction, "channel", None)
            channel_id = None
            channel_name = None
            if channel:
                try:
                    channel_id = int(channel.id)
                    channel_name = str(getattr(channel, "name", ""))
                except Exception:
                    pass

            # Safe extraction of component data
            component_type = None
            component_label = None
            try:
                data = getattr(interaction, "data", None)
                if isinstance(data, dict):
                    comp_type = data.get("component_type")
                    if comp_type is not None:
                        component_type = str(comp_type)
                    
                    custom_id = data.get("custom_id")
                    if custom_id:
                        component_label = str(custom_id)
            except Exception:
                pass

            # Safe defaults
            context_type = "Guild" if guild_id else "DM"
            location = channel_name if guild_id and channel_name else "DM"

            entry = {
                "ts": now,
                "status": "ok",
                "error": None,
                "user_id": user_id,
                "user_tag": user_tag,
                "guild_id": guild_id,
                "guild_name": guild_name,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "context": context_type,
                "location": location,
                "command": "Button/Component",
                "args": f"Type: {component_type or 'Unknown'}, Label: {component_label or 'Unknown'}",
                "raw": None,
            }
            return entry
        except Exception:
            return None

    def _build_audit_entry(
        self,
        interaction: discord.Interaction | None = None,
        command: app_commands.Command | None = None,
        status: str = "ok",
        error: str | None = None,
        ctx: commands.Context | None = None,
    ) -> dict | None:
        """Create a normalized audit entry from an interaction or prefix command context."""
        try:
            now = datetime.now(timezone.utc)
            # Determine source objects
            user = None
            guild = None
            channel = None
            if interaction is not None:
                user = getattr(interaction, "user", None)
                guild = getattr(interaction, "guild", None)
                channel = getattr(interaction, "channel", None)
            elif ctx is not None:
                user = getattr(ctx, "author", None)
                guild = getattr(ctx, "guild", None)
                channel = getattr(ctx, "channel", None)

            # Basics with safe conversion
            user_id = None
            user_tag = None
            if user:
                try:
                    user_id = int(user.id)
                    user_tag = str(user)
                except Exception:
                    pass
            
            guild_id = None
            guild_name = None
            if guild:
                try:
                    guild_id = int(guild.id)
                    guild_name = str(guild.name)
                except Exception:
                    pass
            
            channel_id = None
            channel_name = None
            if channel:
                try:
                    channel_id = int(channel.id)
                    channel_name = str(getattr(channel, "name", ""))
                except Exception:
                    pass

            # Command name and args with safe extraction
            cmd_name = None
            args_str = None
            raw_content = None
            
            if interaction is not None:
                try:
                    if command:
                        cmd_name = str(command.name)
                    elif hasattr(interaction, "command") and interaction.command:
                        cmd_name = str(interaction.command.name)
                except Exception:
                    pass
                
                # Try to format options from raw data
                try:
                    data = getattr(interaction, "data", None)
                    if isinstance(data, dict):
                        if not cmd_name:
                            cmd_name = str(data.get("name", ""))
                        args_str = self._format_interaction_options(data.get("options"))
                except Exception:
                    pass
                    
            if ctx is not None:
                try:
                    cm = getattr(ctx, "command", None)
                    if cm:
                        cmd_name = getattr(cm, "qualified_name", None) or getattr(cm, "name", None)
                        if cmd_name:
                            cmd_name = str(cmd_name)
                except Exception:
                    pass
                
                try:
                    msg = getattr(ctx, "message", None)
                    if msg:
                        raw_content = str(getattr(msg, "content", ""))
                        if raw_content and len(raw_content) > 140:
                            raw_content = raw_content[:139] + "…"
                except Exception:
                    pass

            # Context type and location with safe defaults
            context_type = "Guild" if guild_id else "DM"
            location = channel_name if guild_id and channel_name else "DM"

            # Build entry with validated data
            entry = {
                "ts": now,
                "status": str(status or "ok"),
                "error": str(error) if error else None,
                "user_id": user_id,
                "user_tag": user_tag,
                "guild_id": guild_id,
                "guild_name": guild_name,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "context": context_type,
                "location": location,
                "command": cmd_name,
                "args": args_str,
                "raw": raw_content,
            }
            return entry
        except Exception:
            return None

    async def _jsk_owner_only(self, ctx: commands.Context) -> bool:
        # Allow only bot owner to run Jishaku commands
        try:
            cmd = getattr(ctx, "command", None)
            if cmd:
                qn = getattr(cmd, "qualified_name", None) or getattr(cmd, "name", None)
                if qn and qn.startswith("jsk"):
                    if self.owner_id is None:
                        return False
                    try:
                        return int(ctx.author.id) == int(self.owner_id)
                    except Exception:
                        return False
            return True
        except Exception:
            return True

    def _build_owner_stats_embed(self, title: str | None = None, extra_note: str | None = None) -> discord.Embed:
        """Build the stats embed via General cog's helper when available, with a safe fallback."""
        try:
            cog = self.get_cog("General")
            if cog and hasattr(cog, "build_stats_embed"):
                # General.build_stats_embed returns a discord.Embed
                embed = cog.build_stats_embed(title=title, extra_note=extra_note)
                if isinstance(embed, discord.Embed):
                    return embed
        except Exception as e:
            try:
                self.logger.warning(f"Owner DM: Failed to build stats via General cog, using fallback: {e!r}")
            except Exception:
                pass
        # Fallback embed
        embed = discord.Embed(
            title=title or "Bot Stats",
            description=(extra_note or "Automated owner report"),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        try:
            uname = os.name
        except Exception:
            uname = "unknown"
        embed.add_field(name="Runtime", value=f"Uptime since: {self.start_time:%Y-%m-%d %H:%M:%S UTC}", inline=False)
        embed.add_field(name="Version", value=f"discord.py {discord.__version__} | OS: {uname}", inline=False)
        if self.user:
            embed.set_author(name=str(self.user), icon_url=getattr(self.user.display_avatar, "url", discord.Embed.Empty))
        embed.set_footer(text="Owner notifications | Fallback view")
        return embed

    async def _send_owner_stats_dm(self, title: str, extra_note: str | None = None) -> None:
        """Send a DM with the stats embed to the configured bot owner."""
        try:
            owner_id = int(self.owner_id)
        except Exception:
            owner_id = 0
        if not owner_id:
            return
        # Resolve owner user
        user: discord.User | None = None
        try:
            user = self.get_user(owner_id)
        except Exception:
            user = None
        if user is None:
            try:
                user = await self.fetch_user(owner_id)
            except Exception:
                user = None
        if user is None:
            try:
                self.logger.warning("Owner DM: Could not resolve owner user; skipping notification.")
            except Exception:
                pass
            return
        # Build embed
        embed = self._build_owner_stats_embed(title=title, extra_note=extra_note)
        # Send DM
        try:
            await user.send(embed=embed)
        except Exception as e:
            try:
                self.logger.warning(f"Owner DM: Failed to send embed, attempting text fallback: {e!r}")
            except Exception:
                pass
            try:
                content = f"{title}\n{extra_note or ''}"
                await user.send(content)
            except Exception:
                # Swallow DM failures
                pass

    async def _owner_dm_loop(self) -> None:
        """Background task to send hourly stats DM to the bot owner."""
        try:
            await self.wait_until_ready()
        except Exception:
            # If waiting fails, still attempt loop
            pass
        while True:
            try:
                # Respect client shutdown
                if self.is_closed():
                    break
            except Exception:
                # If check fails, continue
                pass
            # Sleep for one hour
            try:
                await asyncio.sleep(60 * 60)
            except Exception:
                # If sleep is interrupted, continue loop
                pass
            try:
                if self.is_closed():
                    break
            except Exception:
                pass
            # Send hourly stats
            try:
                await self._send_owner_stats_dm(
                    title="⏰ Hourly Bot Stats",
                    extra_note="Automated hourly report to owner.",
                )
            except Exception as e:
                try:
                    self.logger.warning(f"Owner DM: Hourly report failed: {e!r}")
                except Exception:
                    pass


    async def close(self):
        """Properly close the bot and clean up resources."""
        try:
            self.logger.info("Bot shutdown initiated. Cleaning up resources...")
            
            # Stop all players and disconnect from voice channels
            try:
                for guild in self.guilds:
                    if guild.voice_client:
                        await guild.voice_client.disconnect(force=True)
            except Exception as e:
                self.logger.warning(f"Error disconnecting voice clients: {e}")
            
            # Disconnect all Lavalink nodes
            try:
                if hasattr(self, 'node_pool') and self.node_pool:
                    for node in self.node_pool.nodes:
                        try:
                            await node.disconnect()
                            self.logger.info(f"Disconnected Lavalink node: {node.label}")
                        except Exception as e:
                            self.logger.warning(f"Error disconnecting node {node.label}: {e}")
            except Exception as e:
                self.logger.warning(f"Error during Lavalink cleanup: {e}")
            
            # Close the bot's HTTP session
            try:
                await super().close()
                self.logger.info("Bot shutdown completed successfully.")
            except Exception as e:
                self.logger.error(f"Error during bot close: {e}")
                
        except Exception as e:
            self.logger.error(f"Critical error during shutdown: {e}")


def main():
    bot = Bot()
    bot.logger.info("Starting bot...")
    bot.run(bot.config.token)


if __name__ == "__main__":
    main()
