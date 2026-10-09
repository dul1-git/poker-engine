# Local Poker Engine

A lightweight, mobile-first web app to track chips and state for a live physical poker game.

## Features
- **Player View**: Mobile-responsive UI showing current chips, pot, to-call amount, and turn-based action buttons (Fold, Call, Raise).
- **Dealer Dashboard**: Admin view to start hands, force advance streets, end hands, and override chips.
- **Side Pot Calculation**: When the hand ends and the dealer selects the winner(s), the engine automatically calculates side pots based on player investments if anyone was all-in.
- **Real-time**: Powered by Flask-SocketIO.

## Running Locally

1. Set up a Python environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python app.py
   ```

3. **Connecting Devices**:
   - The server binds to `0.0.0.0:5000` by default.
   - Find your computer's local IP address (e.g., `192.168.1.100` on Linux/macOS using `ifconfig` or `ip a`, or `ipconfig` on Windows).
   - On the dealer's device (tablet or laptop), open a browser and go to `http://<YOUR_IP>:5000/dealer`.
   - Have all players connect to your Wi-Fi network and go to `http://<YOUR_IP>:5000/` on their smartphones.

## How to Play
1. Players type their name and join.
2. The Dealer waits for everyone to join, then clicks **Start Hand**. This automatically posts Small Blind and Big Blind and moves the turn to the UTG player.
3. Players tap actions on their phones. The UI will only show buttons when it's their turn.
4. Betting automatically moves to the next street (Flop, Turn, River) when all players match the bet or fold. The Dealer can also manually advance it via **Next Street**.
5. When the physical hand is complete, the Dealer clicks **End Hand**.
6. The Dealer looks at the physical cards, selects the winning player(s) in the dashboard, and clicks **Award Pot**. The app automatically distributes the chips, including complex side pots if short stacks went all-in.
