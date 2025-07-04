# -*- coding: utf-8 -*-
from flask import Flask, request

app = Flask(__name__)

@app.route('/callback')
def linkedin_callback():
    code = request.args.get('code')
    if code:
       print(f"\nAuthorization code received: {code}")
       return f"Authorization code received: {code}<br>You can now close this window."
    return "No authorization code received."

if __name__ == "__main__":
    app.run(port=8000)

