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
import threading
from anjani import main

app = Flask(__name__)

@app.route('/')
def index():
    return 'Hello, World!'

if __name__ == "__main__":
    thread1 = threading.Thread(target=main.start)
    thread2 = threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 8080})
    thread1.start()
    thread2.start()
