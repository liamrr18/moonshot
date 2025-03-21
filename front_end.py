import pyautogui
pyautogui.FAILSAFE = False
import time, pytesseract, cv2, numpy as np, mss, re, sys, keyboard
from colorama import init, Fore, Style

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

PLAY_BUTTON_REGION = (314, 1275, 482, 41)
PLAY_AND_EJECT_BUTTON = (543, 1295)
BET_AMOUNT_FIELD = (700, 1235)

MULTIPLIER_REGION = {'top':285, 'left':434, 'width':350, 'height':150}
PLAYER_LIST_REGION = (1091, 181, 1449, 1199)

FAST_TYPE_DELAY = 0.03
init(autoreset=True)

in_round = False
MIN_VALID_MULTIPLIER = 1.0
LOG_FILE = "crash_times.txt"

def check_nuke():
    while True:
        if keyboard.is_pressed('f9'):
            sys.exit(0)
        time.sleep(0.1)

def morph_close_and_ocr(gray_img):
    kernel = np.ones((3,3), np.uint8)
    closed = cv2.morphologyEx(gray_img, cv2.MORPH_CLOSE, kernel)
    text = pytesseract.image_to_string(
        closed,
        config="--psm 7 -c tessedit_char_whitelist=0123456789."
    )
    return text.strip().replace(" ", "")

def extract_text(img):
    """
    OCR for final crash text e.g. "1.50x"
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5,5), 0)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    return pytesseract.image_to_string(
        gray, config='--psm 6 -c tessedit_char_whitelist=0123456789.xX'
    ).strip()

def extract_multiplier_value(img):
    """
    Returns a float multiplier if valid, else None.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    text = morph_close_and_ocr(gray)
    try:
        val = float(text)
        if val < 1.0 or val > 9999:
            return None
        return val
    except:
        return None

def extract_multiplier(text):
    m = re.search(r'([0-9]+\.[0-9]+)', text)
    return float(m.group(1)) if m else None

def log_crash(mult):
    with open(LOG_FILE, "a") as f:
        f.write(f"{mult:.2f},")

def read_play_button_text():
    screenshot = pyautogui.screenshot(region=PLAY_BUTTON_REGION)
    raw_txt = pytesseract.image_to_string(
        np.array(screenshot),
        config='--psm 7'
    )
    return raw_txt.strip().lower() if raw_txt else ""

def get_game_state():
    """
    - If 'cancel' & 'play' => 'entered'
    - If 'eject' => 'round_in_progress'
    - If 'play next' or 'play' => 'not_entered'
    - else => 'unknown'
    """
    txt = read_play_button_text()
    if "cancel" in txt and "play" in txt:
        return "entered"
    elif "eject" in txt:
        return "round_in_progress"
    elif "play next" in txt or "play" in txt:
        return "not_entered"
    else:
        return "unknown"

def is_bet_placed():
    return in_round

def read_player_list():
    screenshot = pyautogui.screenshot(region=PLAYER_LIST_REGION)
    img = np.array(screenshot)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    text = pytesseract.image_to_string(gray, config='--psm 6')
    lines = text.splitlines()
    data = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            username = parts[0]
            try:
                mult = float(parts[1].replace('x',''))
            except:
                mult = None
            try:
                bet = float(parts[2])
            except:
                bet = None
            data.append({"username": username, "multiplier": mult, "bet": bet})
    return data

def read_median_multiplier(sct, attempts=7, inner_samples=3):
    """
    Collect multiple reads in quick succession, each 'read_max_multiplier()'
    collecting 'inner_samples'. Then we take the median across all attempts.
    This filters out spurious single reads like '5.0x' from OCR noise.
    """
    vals = []
    for _ in range(attempts):
        val = read_max_multiplier(sct, samples=inner_samples, delay=0.005)
        if val is not None and val >= MIN_VALID_MULTIPLIER:
            vals.append(val)
        time.sleep(0.005)

    if not vals:
        return None
    # Spurious read filter: use median, so random outliers won't mislead us
    vals.sort()
    median = vals[len(vals)//2]
    return median

def read_max_multiplier(sct, samples=5, delay=0.02):
    """
    Reads the multiplier region multiple times quickly & returns the MAX reading.
    """
    vals = []
    for _ in range(samples):
        screenshot = sct.grab(MULTIPLIER_REGION)
        img = np.array(screenshot)
        val = extract_multiplier_value(img)
        if val is not None and val >= MIN_VALID_MULTIPLIER:
            vals.append(val)
        time.sleep(delay)
    return max(vals) if vals else None

def predictive_offset(target):
    """
    Example: subtract a small offset so we 'fire' earlier,
    hoping to land near the actual target after reaction time.

    - If target < 1.3, no offset
    - If 1.3 <= target < 2.0 => subtract 0.05
    - If 2.0 <= target < 3.0 => subtract 0.10
    - If target >= 3.0 => subtract 0.20
    Then clamp final to at least 1.0
    """
    if target < 1.3:
        return target
    elif target < 2.0:
        adj = target - 0.05
    elif target < 3.0:
        adj = target - 0.10
    else:
        adj = target - 0.20

    return max(adj, 1.0)

def place_bet(amount, eject_at):
    """
    Type the bet, single click to place. If we see 'entered' => proceed.
    If it reverts to 'not_entered', that means the round ended => we lost.
    """
    global in_round
    if in_round:
        return

    # Type the bet
    pyautogui.click(BET_AMOUNT_FIELD)
    time.sleep(FAST_TYPE_DELAY)
    for _ in range(10):
        pyautogui.press('backspace')
    pyautogui.write(str(int(amount)), interval=FAST_TYPE_DELAY)

    print(f"Placing bet: {amount:.2f}, Eject target: {eject_at:.2f}")
    pyautogui.click(PLAY_AND_EJECT_BUTTON)
    time.sleep(0.2)  # Minimal wait for the UI to switch states

    while True:
        state = get_game_state()
        if state == "entered":
            in_round = True
            print("Bet accepted. Waiting to eject...")
            wait_for_eject(eject_at)
            return

        if state == "not_entered":
            # Means we never got "round_in_progress" => crashed below our target => lost
            print("Bet canceled/round ended before start => lost.")
            in_round = False
            return

        # Otherwise 'unknown' => keep checking quickly
        time.sleep(0.05)

def wait_for_eject(eject_at):
    """
    1) We'll apply a 'predictive offset' so we start trying to eject sooner.
    2) We wait for 'round_in_progress'. If it reverts to 'not_entered' => crashed => we lose.
    3) Once in progress, we read the median multiplier from multiple quick samples.
       If that median >= adjusted target => we click once and exit.
    """
    global in_round
    adjusted_target = predictive_offset(eject_at)
    print(f"Adjusted target for early trigger: {adjusted_target:.2f} (orig {eject_at:.2f})")

    with mss.mss() as sct:
        round_started = False

        while in_round:
            state = get_game_state()

            # If it reverts to 'not_entered', that means the game crashed < ejection => we lose
            if state == "not_entered":
                print("Round ended before we ejected => lost.")
                in_round = False
                return

            if state == "round_in_progress":
                if not round_started:
                    round_started = True
                    # Slightly bigger multiplier region might appear, short micro‐pause:
                    time.sleep(0.1)

                # (2) Filter spurious reads: take the median from multiple samples
                med_val = read_median_multiplier(sct, attempts=5, inner_samples=3)
                if med_val and med_val >= adjusted_target:
                    print(f"Ejecting at {med_val:.2f}x (adjusted target: {adjusted_target:.2f})")
                    pyautogui.click(PLAY_AND_EJECT_BUTTON)
                    time.sleep(0.2)

                    new_state = get_game_state()
                    if new_state not in ("entered", "round_in_progress"):
                        print("Successfully ejected!")
                        in_round = False
                        return
                    else:
                        print("Eject click didn't register or state didn't change. Round presumably continues.")
                        in_round = False
                        return

            # Manual Eject
            if keyboard.is_pressed('e'):
                print("Manual Eject triggered!")
                pyautogui.click(PLAY_AND_EJECT_BUTTON)
                time.sleep(0.2)
                in_round = False
                return

            time.sleep(0.05)

def detect_crash():
    """
    Wait until final crash is stable. Then mark in_round=False and return.
    """
    global in_round
    last_vals = []
    stable = 0

    with mss.mss() as sct:
        while True:
            screenshot = sct.grab(MULTIPLIER_REGION)
            img = np.array(screenshot)
            txt = extract_text(img)
            mult = extract_multiplier(txt)
            if mult is not None:
                if last_vals and abs(mult - last_vals[-1]) < 0.01:
                    stable += 1
                else:
                    stable = 0
                last_vals.append(mult)
                if len(last_vals) > 3:
                    last_vals.pop(0)
                if stable >= 3:
                    crash_val = last_vals[-1]
                    log_crash(crash_val)
                    in_round = False
                    time.sleep(0.3)
                    return crash_val
            time.sleep(0.1)
