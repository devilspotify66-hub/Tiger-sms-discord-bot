"""Discord bot that buys SMS numbers from tiger-sms.com and posts the code."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from tiger_sms import TigerSMSClient, TigerSMSError
from tiger_data import POPULAR_COUNTRIES, POPULAR_SERVICES, country_name, service_name

log = logging.getLogger("tigerbot")

# ---------------- Brand / embed theme ----------------
BRAND_NAME = "Tiger SMS"
BRAND_ICON = "https://tiger-sms.com/favicon-32x32.png"

C_ORANGE = 0xF97316   # purchased / primary brand
C_GREEN = 0x22C55E    # success (code received)
C_AMBER = 0xFBBF24    # balance / info
C_RED = 0xEF4444      # errors / cancelled
C_SLATE = 0x64748B    # neutral info
C_INDIGO = 0x6366F1   # services list
C_TEAL = 0x14B8A6     # countries list


def _brand(embed: discord.Embed, footer: str | None = None) -> discord.Embed:
    embed.set_author(name=BRAND_NAME, icon_url=BRAND_ICON)
    embed.timestamp = datetime.now(timezone.utc)
    if footer:
        embed.set_footer(text=footer, icon_url=BRAND_ICON)
    else:
        embed.set_footer(text="tiger-sms.com", icon_url=BRAND_ICON)
    return embed


def _error_embed(message: str, title: str = "Something went wrong") -> discord.Embed:
    e = discord.Embed(title=title, description=message, colour=C_RED)
    return _brand(e)


class OrderView(discord.ui.View):
    """Buttons attached to a buy/code embed that reveal the activation_id
    or the SMS code (ephemerally) when clicked — so the user can copy them."""

    def __init__(self, db, activation_id: str, timeout: float = 1800.0) -> None:
        super().__init__(timeout=timeout)
        self._db = db
        self._activation_id = activation_id

    @discord.ui.button(label="Copy Code", style=discord.ButtonStyle.primary, emoji="🔑")
    async def copy_code(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        doc = await self._db.tiger_orders.find_one(
            {"activation_id": self._activation_id}, {"_id": 0}
        )
        code = (doc or {}).get("code")
        if code:
            await interaction.response.send_message(str(code), ephemeral=True)
        else:
            status = (doc or {}).get("status", "UNKNOWN")
            await interaction.response.send_message(
                f":hourglass: No code yet — current status: `{status}`.",
                ephemeral=True,
            )

    @discord.ui.button(label="Copy Activation ID", style=discord.ButtonStyle.secondary, emoji="🆔")
    async def copy_activation(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(self._activation_id, ephemeral=True)


def _get_env(name: str, default: Optional[str] = None) -> str:
    v = os.environ.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {name}")
    return v


class TigerBot(commands.Bot):
    def __init__(self, tiger: TigerSMSClient, db) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=os.environ.get("DISCORD_COMMAND_PREFIX", "!"),
            intents=intents,
            help_command=None,
        )
        self.tiger = tiger
        self.db = db
        self.default_country = os.environ.get("DEFAULT_COUNTRY", "33")
        self.poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
        self.poll_timeout = int(os.environ.get("POLL_TIMEOUT_SECONDS", "1200"))

    async def setup_hook(self) -> None:
        await self.add_cog(TigerCog(self))
        try:
            synced = await self.tree.sync()
            log.info("Synced %d slash command(s)", len(synced))
        except Exception as e:
            log.exception("Slash sync failed: %s", e)


class TigerCog(commands.Cog):
    def __init__(self, bot: TigerBot) -> None:
        self.bot = bot

    # ---------------- Shared helpers ----------------
    async def _record(self, doc: dict) -> None:
        try:
            await self.bot.db.tiger_orders.insert_one(doc)
        except Exception as e:  # pragma: no cover
            log.warning("DB insert failed: %s", e)

    async def _update(self, activation_id: str, update: dict) -> None:
        try:
            await self.bot.db.tiger_orders.update_one(
                {"activation_id": activation_id}, {"$set": update}
            )
        except Exception as e:  # pragma: no cover
            log.warning("DB update failed: %s", e)

    async def _do_buy(self, send, user_id: int, service: str, country: Optional[str]) -> None:
        country = country or self.bot.default_country
        try:
            activation_id, phone = await self.bot.tiger.get_number(service, country)
        except TigerSMSError as e:
            await send(embed=_error_embed(f"tiger-sms error: `{e}`", "Purchase failed"))
            return
        except Exception as e:
            await send(embed=_error_embed(f"Request failed: `{e}`", "Purchase failed"))
            return

        created = datetime.now(timezone.utc).isoformat()
        await self._record({
            "activation_id": activation_id,
            "phone": phone,
            "service": service,
            "country": country,
            "user_id": str(user_id),
            "status": "WAITING",
            "code": None,
            "created_at": created,
        })

        embed = discord.Embed(
            title="🐯  Number purchased",
            description=f"Waiting for an SMS on `+{phone}`…",
            colour=C_ORANGE,
        )
        embed.add_field(name="Service", value=f"{service_name(service)}\n`{service}`", inline=True)
        embed.add_field(name="Country", value=f"{country_name(country)}\n`{country}`", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # spacer for clean 2+1 grid
        embed.add_field(name="Phone number", value=f"```+{phone}```", inline=False)
        embed.add_field(name="Activation ID", value=f"`{activation_id}`", inline=False)
        _brand(
            embed,
            footer=f"Polling every {self.bot.poll_interval}s • up to {self.bot.poll_timeout//60} min",
        )
        view = OrderView(self.bot.db, activation_id, timeout=self.bot.poll_timeout + 600)
        await send(embed=embed, view=view)

        # Poll for code in background so command returns immediately.
        asyncio.create_task(self._poll_for_code(send, activation_id, phone, service, country))

    async def _poll_for_code(self, send, activation_id: str, phone: str, service: str, country: str) -> None:
        deadline = asyncio.get_event_loop().time() + self.bot.poll_timeout
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(self.bot.poll_interval)
            try:
                status, code = await self.bot.tiger.get_status(activation_id)
            except TigerSMSError as e:
                await self._update(activation_id, {"status": "ERROR", "error": str(e)})
                await send(embed=_error_embed(
                    f"Status check failed for `{activation_id}`\n`{e}`",
                    "Status error",
                ))
                return
            except Exception as e:
                log.warning("poll error: %s", e)
                continue

            if status == "STATUS_OK" and code:
                await self._update(activation_id, {"status": "RECEIVED", "code": code})
                try:
                    # mark activation complete so the number is released server-side
                    await self.bot.tiger.set_status(activation_id, 6)
                except Exception:
                    pass
                embed = discord.Embed(
                    title="✅  SMS code received",
                    description=f"Code for `+{phone}`",
                    colour=C_GREEN,
                )
                embed.add_field(name="Code", value=f"```\n{code}\n```", inline=False)
                embed.add_field(name="Service", value=f"{service_name(service)}\n`{service}`", inline=True)
                embed.add_field(name="Country", value=f"{country_name(country)}\n`{country}`", inline=True)
                embed.add_field(name="\u200b", value="\u200b", inline=True)
                embed.add_field(name="Activation ID", value=f"`{activation_id}`", inline=False)
                _brand(embed, footer="Activation completed")
                view = OrderView(self.bot.db, activation_id, timeout=1800)
                await send(embed=embed, view=view)
                return
            if status == "ACCESS_CANCEL":
                await self._update(activation_id, {"status": "CANCELLED"})
                cancel_embed = discord.Embed(
                    title="⛔  Activation cancelled",
                    description=f"Activation `{activation_id}` was cancelled.",
                    colour=C_RED,
                )
                _brand(cancel_embed)
                await send(embed=cancel_embed)
                return
            # else STATUS_WAIT_CODE / STATUS_WAIT_RETRY — keep polling

        await self._update(activation_id, {"status": "TIMEOUT"})
        to_embed = discord.Embed(
            title="⏰  SMS timeout",
            description=(
                f"No SMS received within **{self.bot.poll_timeout//60} min** for "
                f"`{activation_id}`.\nUse `/cancel {activation_id}` to free the balance."
            ),
            colour=C_SLATE,
        )
        _brand(to_embed)
        await send(embed=to_embed)

    # ---------------- /buy and !buy ----------------
    @commands.hybrid_command(name="buy", description="Buy a phone number from tiger-sms and await the SMS code.")
    @app_commands.describe(
        service="Service code (e.g. tg for Telegram, wa for WhatsApp, go for Google). See /services.",
        country="Country ID (e.g. 33=Colombia, 187=USA). Optional — defaults to env.",
    )
    async def buy(self, ctx: commands.Context, service: str, country: Optional[str] = None) -> None:
        await ctx.defer()  # works for both slash and prefix (noop for prefix)
        await self._do_buy(ctx.send, ctx.author.id, service, country)

    # ---------------- /status ----------------
    @commands.hybrid_command(name="status", description="Check the status of an activation.")
    @app_commands.describe(activation_id="Activation ID returned from /buy.")
    async def status(self, ctx: commands.Context, activation_id: str) -> None:
        await ctx.defer()
        try:
            st, code = await self.bot.tiger.get_status(activation_id)
        except TigerSMSError as e:
            await ctx.send(embed=_error_embed(f"tiger-sms error: `{e}`", "Status check failed"))
            return

        pretty = {
            "STATUS_OK": ("✅ Code received", C_GREEN),
            "STATUS_WAIT_CODE": ("⏳ Waiting for SMS", C_AMBER),
            "STATUS_WAIT_RETRY": ("🔁 Waiting for retry SMS", C_AMBER),
            "ACCESS_CANCEL": ("⛔ Cancelled", C_RED),
        }.get(st, (f"ℹ️ {st}", C_SLATE))

        embed = discord.Embed(title=pretty[0], colour=pretty[1])
        embed.add_field(name="Activation ID", value=f"`{activation_id}`", inline=False)
        embed.add_field(name="Raw status", value=f"`{st}`", inline=True)
        if code:
            embed.add_field(name="Code", value=f"```\n{code}\n```", inline=False)
        _brand(embed)
        await ctx.send(embed=embed)

    # ---------------- /cancel ----------------
    @commands.hybrid_command(name="cancel", description="Cancel an activation and refund the balance.")
    @app_commands.describe(activation_id="Activation ID returned from /buy.")
    async def cancel(self, ctx: commands.Context, activation_id: str) -> None:
        await ctx.defer()
        try:
            res = await self.bot.tiger.set_status(activation_id, 8)
        except TigerSMSError as e:
            await ctx.send(embed=_error_embed(f"tiger-sms error: `{e}`", "Cancel failed"))
            return
        await self._update(activation_id, {"status": "CANCELLED"})
        embed = discord.Embed(
            title="⛔  Activation cancelled",
            description="The number has been released and your balance refunded.",
            colour=C_RED,
        )
        embed.add_field(name="Activation ID", value=f"`{activation_id}`", inline=False)
        embed.add_field(name="API response", value=f"`{res}`", inline=False)
        _brand(embed)
        await ctx.send(embed=embed)

    # ---------------- /balance ----------------
    @commands.hybrid_command(name="balance", description="Show your tiger-sms account balance.")
    async def balance(self, ctx: commands.Context) -> None:
        await ctx.defer()
        try:
            bal = await self.bot.tiger.get_balance()
        except TigerSMSError as e:
            await ctx.send(embed=_error_embed(f"tiger-sms error: `{e}`", "Balance lookup failed"))
            return
        embed = discord.Embed(title="💰  tiger-sms balance", colour=C_AMBER)
        embed.add_field(name="Available", value=f"**₽ {bal:.2f}** RUB", inline=False)
        _brand(embed, footer="Top up at tiger-sms.com")
        await ctx.send(embed=embed)

    # ---------------- /services ----------------
    @commands.hybrid_command(name="services", description="List popular service codes.")
    async def services(self, ctx: commands.Context) -> None:
        items = list(POPULAR_SERVICES.items())
        half = (len(items) + 1) // 2
        col1 = "\n".join(f"`{c:<3}` · {n}" for c, n in items[:half])
        col2 = "\n".join(f"`{c:<3}` · {n}" for c, n in items[half:])
        embed = discord.Embed(
            title="📋  Popular services",
            description="Use the code with `/buy service:<code>`.",
            colour=C_INDIGO,
        )
        embed.add_field(name="\u200b", value=col1 or "\u200b", inline=True)
        embed.add_field(name="\u200b", value=col2 or "\u200b", inline=True)
        _brand(embed, footer="Full catalog: tiger-sms.com/api")
        await ctx.send(embed=embed)

    # ---------------- /countries ----------------
    @commands.hybrid_command(name="countries", description="List popular country IDs.")
    async def countries(self, ctx: commands.Context) -> None:
        items = list(POPULAR_COUNTRIES.items())
        half = (len(items) + 1) // 2
        col1 = "\n".join(f"`{c:>3}` · {n}" for c, n in items[:half])
        col2 = "\n".join(f"`{c:>3}` · {n}" for c, n in items[half:])
        embed = discord.Embed(
            title="🌍  Popular countries",
            description="Use the ID with `/buy service:<code> country:<id>`.",
            colour=C_TEAL,
        )
        embed.add_field(name="\u200b", value=col1 or "\u200b", inline=True)
        embed.add_field(name="\u200b", value=col2 or "\u200b", inline=True)
        _brand(embed, footer="Full catalog: tiger-sms.com/api")
        await ctx.send(embed=embed)

    # ---------------- /help ----------------
    @commands.hybrid_command(name="tigerhelp", description="Show available tiger-sms bot commands.")
    async def tigerhelp(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title="🐯  Tiger SMS Bot",
            description="Buy virtual phone numbers from tiger-sms.com and receive SMS codes right here.",
            colour=C_ORANGE,
        )
        embed.add_field(
            name="Main commands",
            value=(
                "`/buy service [country]` — buy a number & auto-receive the code\n"
                "`/status <activation_id>` — check status of an activation\n"
                "`/cancel <activation_id>` — cancel & refund"
            ),
            inline=False,
        )
        embed.add_field(
            name="Info",
            value=(
                "`/balance` — show tiger-sms balance\n"
                "`/services` — popular service codes\n"
                "`/countries` — popular country IDs"
            ),
            inline=False,
        )
        embed.add_field(
            name="Prefix alternatives",
            value="`!buy`, `!status`, `!cancel`, `!balance`, `!services`, `!countries`",
            inline=False,
        )
        _brand(embed)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.info("Bot ready as %s (id=%s)", self.bot.user, getattr(self.bot.user, "id", "?"))


async def run_bot(db) -> None:
    token = _get_env("DISCORD_BOT_TOKEN")
    api_key = _get_env("TIGER_SMS_API_KEY")
    tiger = TigerSMSClient(api_key)
    bot = TigerBot(tiger, db)
    try:
        await bot.start(token)
    finally:
        await tiger.close()
