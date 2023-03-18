import os
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello_world():
    return "Hello from Flask!"

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=os.environ.get('PORT', 8080))
