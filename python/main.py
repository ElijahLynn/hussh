import time
from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI
from array_state import MicrophoneArray

ui = WebUI()
array = MicrophoneArray()
alert = False

def identify(client, data):
    if isinstance(data, dict):
        array.identify(client, data.get('name', ''))

def level(client, data):
    if array.update(client, data):
        # Receipt acknowledgment only. A single loop controls the MCU for all phones.
        ui.send_message('ack', {'level': data['level'], 'alert': alert}, client)

def stop(client, data):
    array.stop(client)

ui.on_message('identify', identify)
ui.on_message('level', level)
ui.on_message('stop_microphone', stop)
ui.on_disconnect(array.disconnect)

def tick():
    global alert
    started = time.monotonic()
    snapshot = array.snapshot()
    try:
        Bridge.call('set_level', snapshot['level'], timeout=1)
        alert = bool(Bridge.call('alert_state', timeout=1))
        board_ok = True
    except Exception as error:
        alert = False
        board_ok = False
        print('Board communication unavailable:', type(error).__name__, flush=True)
    snapshot.update({'alert': alert, 'board_ok': board_ok})
    ui.send_message('array_state', snapshot)
    time.sleep(max(0, 0.1 - (time.monotonic() - started)))

App.run(user_loop=tick)
