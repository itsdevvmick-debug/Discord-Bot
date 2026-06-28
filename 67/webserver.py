from flask import Flask
from threading import Thread

from config import Config

app = Flask('')

@app.route('/')
def home():
    return f"{Config.BRAND_NAME} bot is alive!"

def run():
    app.run(host='0.0.0.0', port=Config.RENDER_PORT, use_reloader=False)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()
