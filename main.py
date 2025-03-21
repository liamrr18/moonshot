import threading, time, sys
from front_end import (
    place_bet,
    detect_crash,
    check_nuke,
    get_game_state,
    is_bet_placed,
    read_player_list
)
from back_end import get_next_bet, update_balance
from colorama import Fore, Style

def load_crash_history():
    try:
        with open("crash_times.txt", "r") as f:
            data = f.read().strip().split(",")
            return [float(x) for x in data if x.strip().replace(".", "", 1).isdigit()]
    except:
        return []

def main_loop():
    balance = float(input("Starting balance: "))
    crash_history = load_crash_history()

    # Optionally gather some initial data if you want
    while len(crash_history) < 5:
        cval = detect_crash()
        if cval is not None:
            crash_history.append(cval)

    spectating = True

    while True:
        state = get_game_state()
        # If we want to watch the first round or so
        if spectating:
            cval = detect_crash()
            if cval is not None:
                crash_history.append(cval)
            spectating = False
            continue

        # Place a bet if not entered & we're not currently in a round
        if state == "not_entered" and not is_bet_placed():
            players = read_player_list()
            # Pick bet/eject using your Q-table logic
            recent_crashes = tuple(crash_history[-10:])
            bet, eject = get_next_bet(recent_crashes, players)
            place_bet(bet, eject)

        # If the round is in progress or 'entered', wait for the crash
        elif state in ("round_in_progress", "entered"):
            cval = detect_crash()
            if cval:
                crash_history.append(cval)
                if len(crash_history) > 50:
                    crash_history.pop(0)

                # For final stats, we re-fetch bet/eject or store them globally
                # We'll just guess them if not stored
                final_bet = bet if 'bet' in locals() else 10
                final_eject = eject if 'eject' in locals() else 2.0

                balance = update_balance(cval, final_bet, final_eject, balance)
                result = "WIN" if cval >= final_eject else "LOSS"
                color = Fore.GREEN if result == "WIN" else Fore.RED
                print(f"{color}Crash: {cval:.2f}x | Bet: {final_bet:.2f} "
                      f"| Eject: {final_eject:.2f}x | Balance: {balance:.2f} "
                      f"| {result}{Style.RESET_ALL}")

        else:
            # Unknown or not recognized => short pause, re-check next loop
            time.sleep(0.25)

def run_bot():
    try:
        # Start a background thread to let F9 kill the script
        threading.Thread(target=check_nuke, daemon=True).start()
        main_loop()
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    run_bot()
