"""
Legacy compatibility alias — do not use as primary entrypoint.

The canonical way to start the bot is:

    python bot.py

This file exists only for backward compatibility and delegates directly
to bot.main(). It is not used by start.sh or render.yaml.
"""



from bot import main

if __name__ == "__main__":
    main()