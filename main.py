import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, \
    CallbackQueryHandler, filters
from config import BOT_TOKEN
import socket
from src.bot.handlers import start_handler, menu_handler, \
    package_selection_callback, verify_join_callback, claim_reward_callback


socket.setdefaulttimeout(30)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        logger.info("Initializing NetRah Dynamic Order Engine...")
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        PRIVATE = filters.ChatType.PRIVATE

        # Handelers
        application.add_handler(CommandHandler("start", start_handler,
                                               filters=PRIVATE))
        application.add_handler(
            CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))

        application.add_handler(CallbackQueryHandler(package_selection_callback,
                                                     pattern="^buy_pkg:"))

        application.add_handler(CallbackQueryHandler(claim_reward_callback,
                                             pattern="^claim_referral_reward$"))
        application.add_handler(
            MessageHandler(PRIVATE & filters.TEXT & ~filters.COMMAND, menu_handler))

        logger.info("NetRah Bot is listening for commerce requests...")
        application.run_polling()
    except Exception as e:
        logger.critical(f"Critical error during bot execution: {e}")


if __name__ == "__main__":
    main()


