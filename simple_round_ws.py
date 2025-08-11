import os
import json
import threading
import ssl
import certifi
import websocket
from flask import Flask, jsonify
from flask_socketio import SocketIO
from autodarts_keycloak_client import AutodartsKeycloakClient

AUTODARTS_WEBSOCKET_URL = 'wss://api.autodarts.io/ms/v0/subscribe'

app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')

latest_round = {}

def get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'Missing environment variable: {name}')
    return value


def run_autodarts_ws():
    os.environ['SSL_CERT_FILE'] = certifi.where()
    kc = AutodartsKeycloakClient(
        username=get_env('AUTODARTS_USERNAME'),
        password=get_env('AUTODARTS_PASSWORD'),
        client_id=get_env('AUTODARTS_CLIENT_ID'),
        client_secret=get_env('AUTODARTS_CLIENT_SECRET'),
    )
    kc.start()
    board_id = get_env('AUTODARTS_BOARD_ID')

    def on_open(ws):
        subscribe = {
            'channel': 'autodarts.boards',
            'type': 'subscribe',
            'topic': f'{board_id}.matches',
        }
        ws.send(json.dumps(subscribe))

    def on_message(ws, message):
        global latest_round
        msg = json.loads(message)
        channel = msg.get('channel')
        data = msg.get('data', {})

        if channel == 'autodarts.boards':
            if data.get('event') == 'start' and 'id' in data:
                match_id = data['id']
                subscribe_match = {
                    'channel': 'autodarts.matches',
                    'type': 'subscribe',
                    'topic': f'{match_id}.state',
                }
                ws.send(json.dumps(subscribe_match))
        elif channel == 'autodarts.matches':
            turns = data.get('turns') or []
            if turns:
                latest_round = turns[0]
                socketio.emit('round', latest_round)

    def on_error(ws, error):
        print('WebSocket error:', error)

    def on_close(ws, close_status_code, close_msg):
        print('WebSocket closed')

    headers = {'Authorization': f'Bearer {kc.access_token}'}
    ws = websocket.WebSocketApp(
        AUTODARTS_WEBSOCKET_URL,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    sslopt = {'cert_reqs': ssl.CERT_REQUIRED, 'ca_certs': certifi.where()}
    ws.run_forever(sslopt=sslopt)


@app.route('/round')
def get_round():
    return jsonify(latest_round)


def main():
    threading.Thread(target=run_autodarts_ws, daemon=True).start()
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8080'))
    socketio.run(app, host=host, port=port)


if __name__ == '__main__':
    main()

