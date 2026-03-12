"""
Entrypoint principal del chatbot.

Este archivo es el punto de arranque del sistema. Su única función es
iniciar el bot importando la función `main()` del módulo `bot.py`.

Se utiliza para ejecutar el bot desde terminal con:

    python main.py

Mantener este archivo simple permite separar claramente el arranque del
sistema de la lógica del bot.
"""



from bot import main

if __name__ == "__main__":
    main()