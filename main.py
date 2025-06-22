from machine import Pin, SoftI2C
from i2c_lcd import I2cLcd
import time
import esp32
import sound
import _thread

# Инициализация LCD и кнопок
i2c = SoftI2C(sda=Pin(21), scl=Pin(22), freq=400000)
lcd = I2cLcd(i2c, 0x27, 2, 16)
nvs = esp32.NVS("settings")

buttons = {
    'up': Pin(13, Pin.IN, Pin.PULL_UP),
    'down': Pin(12, Pin.IN, Pin.PULL_UP),
    'left': Pin(14, Pin.IN, Pin.PULL_UP),
    'right': Pin(27, Pin.IN, Pin.PULL_UP),
    'enter': Pin(26, Pin.IN, Pin.PULL_UP)
}

class State:
    def __init__(self):
        self.volume = 5
        self.melody_playing = False
        self.melody_paused = False
        self.current_melody = 0
        self.note_index = 0
        self.show_stop_option = False
        self.current_menu = 'main'
        self.menu_stack = ['main']
        self.selected_item = 0
        self.last_button_time = 0
        self.display_mode = "normal"
        self.paused_blink = False

state = State()

melodies = [
    {'name': "Mario", 'data': sound.mario, 'speed': 150},
    {'name': "Twinkle", 'data': sound.twinkle, 'speed': 600},
    {'name': "Jingle", 'data': sound.jingle, 'speed': 250}
]

def init_custom_chars():
    chars = [
        [0x00]*8, [0x10]*8, [0x18]*8,
        [0x1C]*8, [0x1E]*8, [0x1F]*8
    ]
    for i, c in enumerate(chars):
        lcd.custom_char(i, bytearray(c))

def get_volume_duty(level):
    level = max(0, min(10, level))
    scale = [1000, 2000, 3000, 4000, 5000,
             6500, 8000, 10000, 13000, 17000, 20000]
    return scale[level]

def load_volume():
    try:
        state.volume = nvs.get_i32("volume")
        if not 0 <= state.volume <= 10:
            state.volume = 5
    except:
        state.volume = 5

def save_volume():
    nvs.set_i32("volume", state.volume)
    nvs.commit()

def melody_thread():
    while True:
        if state.melody_playing:
            melody = melodies[state.current_melody]
            data = melody['data']
            speed = melody['speed']

            while state.note_index < len(data):
                if not state.melody_playing:
                    state.note_index = 0
                    break

                if state.melody_paused:
                    time.sleep(0.05)
                    continue

                note = data[state.note_index]

                if note <= 0 or note > 20000:
                    sound.buzzer.pwm.duty_u16(0)
                else:
                    duty = get_volume_duty(state.volume)
                    try:
                        sound.buzzer.pwm.freq(note)
                        sound.buzzer.pwm.duty_u16(duty)
                    except ValueError:
                        sound.buzzer.pwm.duty_u16(0)

                state.note_index += 1
                time.sleep_ms(speed)

            sound.buzzer.pwm.duty_u16(0)
            state.melody_playing = False
            state.melody_paused = False
            state.note_index = 0
            state.display_mode = "normal"
            display_menu()
        else:
            time.sleep(0.1)

def pause_blink_thread():
    while True:
        if state.melody_paused:
            state.paused_blink = not state.paused_blink
            display_player_screen()
        time.sleep(0.5)

def display_player_screen():
    lcd.clear()
    melody = melodies[state.current_melody]

    if state.display_mode == "paused":
        lcd.putstr(melody['name'][:16])
        lcd.move_to(0, 1)
        lcd.putstr("Paused" if state.paused_blink else "      ")
        return

    if state.display_mode == "resumed":
        lcd.putstr(melody['name'][:16])
        state.display_mode = "normal"
        return

    if state.show_stop_option:
        lcd.putstr(melody['name'][:16])
        lcd.move_to(0, 1)
        lcd.putstr("> Stop")
        return

    # Стандартное отображение громкости
    volume_percent = int((state.volume / 10.0) * 100)
    lcd.putstr(f"VOL: {volume_percent:3d}%")
    lcd.move_to(0, 1)
    progress = int((state.volume / 10.0) * 16)
    for i in range(16):
        lcd.putchar(chr(5) if i < progress else chr(0))

def display_menu():
    lcd.clear()
    if state.current_menu == 'main':
        lcd.putstr("Main Menu")
        items = ["1.Select Melody", "2.Settings"]
    elif state.current_menu == 'melodies':
        lcd.putstr("Select Melody")
        items = ["1.1 Mario", "1.2 Twinkle", "1.3 Jingle", "1.4 Back"]
    elif state.current_menu == 'settings':
        lcd.putstr("Settings")
        items = ["2.1 Reset Vol", "2.2 Backlight", "2.3 Back"]
    elif state.current_menu == 'backlight':
        lcd.putstr("Backlight")
        items = ["2.2.1 ON", "2.2.2 OFF", "2.2.3 Back"]
    else:
        items = []

    if items:
        lcd.move_to(0, 1)
        lcd.putstr(">" + items[state.selected_item][:15])

def handle_buttons():
    current_time = time.ticks_ms()
    if current_time - state.last_button_time < 200:
        return
    state.last_button_time = current_time

    if state.melody_playing:
        if not buttons['left'].value() and state.volume > 0 and not state.show_stop_option:
            state.volume -= 1
            save_volume()
            display_player_screen()
        elif not buttons['right'].value() and state.volume < 10 and not state.show_stop_option:
            state.volume += 1
            save_volume()
            display_player_screen()
        elif not buttons['enter'].value():
            if state.show_stop_option:
                state.melody_playing = False
                state.melody_paused = False
                state.note_index = 0
                state.show_stop_option = False
                state.display_mode = "normal"
                sound.buzzer.pwm.duty_u16(0)
                display_menu()
            else:
                state.melody_paused = not state.melody_paused
                if state.melody_paused:
                    sound.buzzer.pwm.duty_u16(0)
                    state.display_mode = "paused"
                else:
                    state.display_mode = "resumed"
                display_player_screen()
        elif not buttons['down'].value():
            state.show_stop_option = not state.show_stop_option
            display_player_screen()
        return

    if not buttons['up'].value():
        state.selected_item = max(0, state.selected_item - 1)
        display_menu()
    elif not buttons['down'].value():
        limits = {
            'main': 1,
            'melodies': 3,
            'settings': 2,
            'backlight': 2
        }
        max_index = limits.get(state.current_menu, 0)
        state.selected_item = min(max_index, state.selected_item + 1)
        display_menu()
    elif not buttons['enter'].value():
        execute_menu_action()

def execute_menu_action():
    if state.current_menu == 'main':
        if state.selected_item == 0:
            state.current_menu = 'melodies'
            state.menu_stack.append('melodies')
        elif state.selected_item == 1:
            state.current_menu = 'settings'
            state.menu_stack.append('settings')
        state.selected_item = 0

    elif state.current_menu == 'melodies':
        if state.selected_item in [0, 1, 2]:
            state.current_melody = state.selected_item
            state.melody_playing = True
            state.melody_paused = False
            state.note_index = 0
            state.show_stop_option = False
            state.display_mode = "normal"
            display_player_screen()
        elif state.selected_item == 3:
            state.menu_stack.pop()
            state.current_menu = state.menu_stack[-1]
            state.selected_item = 0

    elif state.current_menu == 'settings':
        if state.selected_item == 0:
            state.volume = 5
            save_volume()
            show_message("Volume Reset")
        elif state.selected_item == 1:
            state.current_menu = 'backlight'
            state.menu_stack.append('backlight')
            state.selected_item = 0
        elif state.selected_item == 2:
            state.menu_stack.pop()
            state.current_menu = state.menu_stack[-1]
            state.selected_item = 0

    elif state.current_menu == 'backlight':
        if state.selected_item == 0:
            lcd.backlight_on()
            show_message("Backlight ON")
        elif state.selected_item == 1:
            lcd.backlight_off()
            show_message("Backlight OFF")
        elif state.selected_item == 2:
            state.menu_stack.pop()
            state.current_menu = state.menu_stack[-1]
            state.selected_item = 0

    display_menu()

def show_message(msg):
    lcd.clear()
    lcd.putstr(msg)
    time.sleep(1)
    display_menu()

def main():
    init_custom_chars()
    load_volume()
    _thread.start_new_thread(melody_thread, ())
    _thread.start_new_thread(pause_blink_thread, ())

    lcd.clear()
    lcd.putstr("Audio Player")
    lcd.move_to(0, 1)
    lcd.putstr("Loading...")
    time.sleep(1)
    display_menu()

    try:
        while True:
            handle_buttons()
            time.sleep(0.02)
    except KeyboardInterrupt:
        sound.buzzer.pwm.duty_u16(0)
        lcd.clear()
        lcd.putstr("Goodbye!")

if __name__ == "__main__":
    main()
