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
            await interaction.response.send_message(
                f"**SMS code** (tap/triple-click to copy):\n```{code}```",
                ephemeral=True,
            )
        else:
            status = (doc or {}).get("status", "UNKNOWN")
            await interaction.response.send_message(
                f":hourglass: No code yet — current status: `{status}`.",
                ephemeral=True,
            )

    @discord.ui.button(label="Copy Activation ID", style=discord.ButtonStyle.secondary, emoji="🆔")
    async def copy_activation(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            f"**Activation ID** (tap/triple-click to copy):\n```{self._activation_id}```",
            ephemeral=True,
        )


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
            await send(f":x: tiger-sms error: `{e}`")
            return
        except Exception as e:
            await send(f":x: Request failed: `{e}`")
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
            title="Number purchased",
            colour=0x2ECC71,
            description=(
                f"**Service:** {service_name(service)} (`{service}`)\n"
                f"**Country:** {country_name(country)} (`{country}`)\n"
                f"**Phone:** `+{phone}`\n"
                f"**Activation ID:** `{activation_id}`"
            ),
        )
        embed.set_footer(text=f"Polling every {self.bot.poll_interval}s for up to {self.bot.poll_timeout//60} min.")
        await send(embed=embed)

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
                await send(f":warning: Status error for `{activation_id}`: `{e}`")
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
                    title="SMS code received",
                    colour=0x3498DB,
                    description=(
                        f"**Phone:** `+{phone}`\n"
                        f"**Service:** {service_name(service)} (`{service}`)\n"
                        f"**Country:** {country_name(country)} (`{country}`)\n"
                        f"**Code:** ```{code}```\n"
                        f"**Activation ID:** `{activation_id}`"
                    ),
                )
                view = OrderView(self.bot.db, activation_id, timeout=1800)
                await send(embed=embed, view=view)
                return
            if status == "ACCESS_CANCEL":
                await self._update(activation_id, {"status": "CANCELLED"})
                await send(f":no_entry: Activation `{activation_id}` was cancelled.")
                return
            # else STATUS_WAIT_CODE / STATUS_WAIT_RETRY — keep polling

        await self._update(activation_id, {"status": "TIMEOUT"})
        await send(
            f":alarm_clock: No SMS received within {self.bot.poll_timeout//60} min for `{activation_id}`. "
            f"Use `/cancel {activation_id}` to free the balance."
        )

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
            await ctx.send(f":x: tiger-sms error: `{e}`")
            return
        msg = f"**Activation `{activation_id}`** — status: `{st}`"
        if code:
            msg += f"\n**Code:** ```{code}```"
        await ctx.send(msg)

    # ---------------- /cancel ----------------
    @commands.hybrid_command(name="cancel", description="Cancel an activation and refund the balance.")
    @app_commands.describe(activation_id="Activation ID returned from /buy.")
    async def cancel(self, ctx: commands.Context, activation_id: str) -> None:
        await ctx.defer()
        try:
            res = await self.bot.tiger.set_status(activation_id, 8)
        except TigerSMSError as e:
            await ctx.send(f":x: tiger-sms error: `{e}`")
            return
        await self._update(activation_id, {"status": "CANCELLED"})
        await ctx.send(f":white_check_mark: Cancelled `{activation_id}` — response: `{res}`")

    # ---------------- /balance ----------------
    @commands.hybrid_command(name="balance", description="Show your tiger-sms account balance.")
    async def balance(self, ctx: commands.Context) -> None:
        await ctx.defer()
        try:
            bal = await self.bot.tiger.get_balance()
        except TigerSMSError as e:
            await ctx.send(f":x: tiger-sms error: `{e}`")
            return
        await ctx.send(f":moneybag: **Balance:** `{bal}` RUB")

    # ---------------- /services ----------------
    @commands.hybrid_command(name="services", description="List popular service codes.")
    async def services(self, ctx: commands.Context) -> None:
        lines = [f"`{c}` — {n}" for c, n in POPULAR_SERVICES.items()]
        embed = discord.Embed(
            title="Popular services",
            description="\n".join(lines),
            colour=0x9B59B6,
        )
        embed.set_footer(text="Full list: https://tiger-sms.com/api#services")
        await ctx.send(embed=embed)

    # ---------------- /countries ----------------
    @commands.hybrid_command(name="countries", description="List popular country IDs.")
    async def countries(self, ctx: commands.Context) -> None:
        lines = [f"`{c}` — {n}" for c, n in POPULAR_COUNTRIES.items()]
        embed = discord.Embed(
            title="Popular countries",
            description="\n".join(lines),
            colour=0xE67E22,
        )
        embed.set_footer(text="Full list: https://tiger-sms.com/api#countries")
        await ctx.send(embed=embed)

    # ---------------- /help ----------------
    @commands.hybrid_command(name="tigerhelp", description="Show available tiger-sms bot commands.")
    async def tigerhelp(self, ctx: commands.Context) -> None:
        txt = (
            "**Tiger-SMS Discord Bot — commands**\n"
            "`/buy service [country]` — purchase a number & await SMS code\n"
            "`/status <activation_id>` — check status of an activation\n"
            "`/cancel <activation_id>` — cancel an activation (refund)\n"
            "`/balance` — show tiger-sms balance\n"
            "`/services` — list popular service codes\n"
            "`/countries` — list popular country IDs\n"
            "Prefix alternative: `!buy`, `!status`, `!cancel`, `!balance`, `!services`, `!countries`"
        )
        await ctx.send(txt)

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
