import torch, torch.nn as nn
import numpy as np, pickle, random

class LSTMPredictor(nn.Module):
    def __init__(self, input_size=1, hidden_size=20, num_layers=1, output_size=1):
        super(LSTMPredictor, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)
    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out[:, -1, :])

model_path = r"C:\Users\liamr\Downloads\new_lstm_crash_predictor_raw.pth"
q_table_path = r"C:\Users\liamr\Downloads\updated_q_table.pkl"

model = LSTMPredictor()
model.load_state_dict(torch.load(model_path))
model.eval()

with open(q_table_path, "rb") as f:
    Q_table = pickle.load(f)

MIN_BET = 2
MAX_BET = 80
MIN_EJECT = 1.5
MAX_EJECT = 3.0

alpha = 0.3
gamma = 0.9
epsilon = 0.5

losing_streak = 0
winning_streak = 0

def get_next_bet(state, player_data):
    global losing_streak, winning_streak
    if state not in Q_table:
        Q_table[state] = {}
        for _ in range(5):
            bet = np.random.uniform(MIN_BET, MAX_BET)
            eject = np.random.uniform(MIN_EJECT, MAX_EJECT)
            Q_table[state][(bet, eject)] = np.random.uniform(-1, 1)
    actions = list(Q_table[state].keys())
    q_vals = np.array([Q_table[state][a] for a in actions])
    risk_factor = 0.7
    probabilities = np.exp(risk_factor * (q_vals - np.max(q_vals)))
    probabilities /= probabilities.sum()
    action = random.choices(actions, weights=probabilities, k=1)[0]
    base_bet, base_eject = action

    # example logic to adjust bet/eject:
    if player_data:
        total = len(player_data)
        cashed = sum(1 for p in player_data if p.get("multiplier") is not None and p.get("multiplier") > 0)
        if total > 0 and (cashed / total) > 0.5:
            base_bet *= 1.5
            base_eject = max(MIN_EJECT, base_eject - 0.2)

    if losing_streak >= 3:
        base_bet *= 1.5
        base_eject = max(MIN_EJECT, base_eject * 0.9)
    if losing_streak >= 5:
        base_bet *= 2.0
        base_eject = max(MIN_EJECT, base_eject * 0.8)
    if losing_streak >= 7:
        base_bet = MAX_BET
        base_eject = MIN_EJECT
    if winning_streak >= 2 or base_eject >= 2.5:
        base_bet = MIN_BET
        base_eject = MAX_EJECT
        winning_streak = 0

    final_bet = min(base_bet, MAX_BET)
    final_eject = max(MIN_EJECT, round(base_eject, 2))
    return final_bet, final_eject

def update_balance(crash, bet, eject, current_balance):
    global Q_table, losing_streak, winning_streak
    reward = (bet * (eject - 1)) if crash >= eject else -bet
    state = tuple(Q_table.keys())[-1] if Q_table else ()
    next_state = state[1:] + (crash,) if state else (crash,)
    if next_state not in Q_table:
        Q_table[next_state] = {}
        for _ in range(5):
            new_bet = np.random.uniform(MIN_BET, MAX_BET)
            new_eject = np.random.uniform(MIN_EJECT, MAX_EJECT)
            Q_table[next_state][(new_bet, new_eject)] = np.random.uniform(-1, 1)
    if (bet, eject) not in Q_table[state]:
        Q_table[state][(bet, eject)] = 0
    best_future_q = max(Q_table[next_state].values(), default=0)
    Q_table[state][(bet, eject)] += alpha * (reward + gamma * best_future_q - Q_table[state][(bet, eject)])
    with open(q_table_path, "wb") as f:
        pickle.dump(Q_table, f)

    if crash >= eject:
        current_balance += bet * (eject - 1)
        losing_streak = 0
        winning_streak += 1
    else:
        current_balance -= bet
        losing_streak += 1
        winning_streak = 0

    return current_balance
