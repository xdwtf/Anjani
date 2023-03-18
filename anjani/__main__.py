"""Bot entry"""
# Copyright (C) 2020 - 2023  UserbotIndo Team, <https://github.com/userbotindo.git>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from flask import Flask
from threading import Thread
from anjani import main
import signal
import sys

app = Flask(__name__)

@app.route("/")
def home():
    # Add your custom logic here
    return "Welcome to my bot!"

def signal_handler(sig, frame):
    print('Received SIGTERM, shutting down...')
    # Stop the bot
    main.stop()
    # Stop the Flask app
    sys.exit(0)

if __name__ == "__main__":
    # Start the bot in a separate thread
    print('Sarting botx...')
    bot_thread = Thread(target=main.start)
    bot_thread.daemon = True
    bot_thread.start()

    # Set up a signal handler for SIGTERM
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the Flask app on port 8080
    app.run(host="0.0.0.0", port=8080)
