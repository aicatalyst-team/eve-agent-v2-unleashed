"""
Eve V2U Telegram Bot — Optional notification + chat bridge.

Set TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID in .env to activate.
Eve will push quest completions and level-ups to your Telegram.
You can also send messages to Eve via Telegram and receive replies.

Install: pip install python-telegram-bot
"""

import asyncio
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger("eve_telegram")


class EveTelegramBot:
    def __init__(
        self,
        token: str,
        allowed_user_id: int,
        run_chat: Optional[Callable] = None,
    ):
        """
        Args:
            token:          Bot token from @BotFather
            allowed_user_id: Your Telegram user ID (whitelist — one user only)
            run_chat:       async callable(session_id, message) → str for chat bridge
        """
        self.token           = token
        self.allowed_user_id = int(allowed_user_id)
        self.run_chat        = run_chat
        self._app            = None

    async def start(self):
        try:
            from telegram import Update
            from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
            return

        self._app = ApplicationBuilder().token(self.token).build()

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.effective_user.id != self.allowed_user_id:
                return
            user_msg = update.message.text or ""
            if not user_msg:
                return
            await update.message.chat.send_action("typing")
            try:
                if self.run_chat:
                    response = await self.run_chat("telegram", user_msg)
                else:
                    response = "Eve is online but chat bridge is not configured."
            except Exception as e:
                response = f"Error: {e}"
            await update.message.reply_text(response[:4096])

        from telegram.ext import MessageHandler, filters
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info(f"🤖 Telegram bot starting (user_id={self.allowed_user_id})")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send(self, message: str):
        """Push a notification to your Telegram."""
        if not self._app:
            return
        try:
            await self._app.bot.send_message(
                chat_id=self.allowed_user_id,
                text=message[:4096],
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")


# ── Module-level singleton ────────────────────────────────────────────────────

_bot: Optional[EveTelegramBot] = None


def get_bot() -> Optional[EveTelegramBot]:
    return _bot


async def init_bot(run_chat: Optional[Callable] = None) -> Optional[EveTelegramBot]:
    """
    Initialize the bot from environment variables.
    Returns None if TELEGRAM_BOT_TOKEN is not set.
    """
    global _bot
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    user_id = os.getenv("TELEGRAM_USER_ID", "").strip()

    if not token or not user_id:
        logger.info("Telegram bot not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_USER_ID not set)")
        return None

    try:
        _bot = EveTelegramBot(token=token, allowed_user_id=int(user_id), run_chat=run_chat)
        await _bot.start()
        logger.info("✅ Telegram bot initialized and polling")
        return _bot
    except Exception as e:
        logger.warning(f"Telegram bot init failed: {e}")
        return None


async def notify(message: str):
    """Send a push notification. No-op if bot is not configured."""
    if _bot:
        await _bot.send(message)
