import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'poker_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

rooms = {} # code -> game_state
player_to_room = {} # sid -> code

def create_initial_state(host_sid):
    return {
        "host_sid": host_sid,
        "players": {},       
        "player_order": [],  
        "dealer_idx": 0,
        "turn_idx": -1,
        "current_bet": 0,
        "pot": 0,
        "phase": "waiting",  
        "blinds": {"sb": 10, "bb": 20},
        "starting_chips": 1000,
        "min_raise": 20
    }

def broadcast_state(code):
    if code not in rooms: return
    state = rooms[code]
    safe_players = {
        sid: {
            "name": p["name"],
            "chips": p["chips"],
            "bet": p["bet"],
            "status": p["status"],
            "total_invested": p["total_invested"],
            "is_turn": (state["player_order"] and state["turn_idx"] >= 0 and state["turn_idx"] < len(state["player_order"]) and state["player_order"][state["turn_idx"]] == sid)
        }
        for sid, p in state["players"].items()
    }
    
    emit('game_update', {
        "room": code,
        "host_sid": state["host_sid"],
        "players": safe_players,
        "player_order": state["player_order"],
        "dealer_idx": state["dealer_idx"],
        "turn_idx": state["turn_idx"],
        "current_bet": state["current_bet"],
        "pot": state["pot"],
        "phase": state["phase"],
        "blinds": state["blinds"]
    }, to=code)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/player')
def player():
    return render_template('player.html')

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    if sid in player_to_room:
        code = player_to_room[sid]
        # Simplification: we don't handle mid-game disconnect logic perfectly in this quick build
        # We just leave them in state so chips aren't lost, or we could fold them.
        pass

@socketio.on('create_room')
def on_create_room(data):
    sid = request.sid
    name = data.get("name")
    code = str(random.randint(1000, 9999))
    while code in rooms:
        code = str(random.randint(1000, 9999))
        
    rooms[code] = create_initial_state(sid)
    rooms[code]["players"][sid] = {
        "name": name,
        "chips": rooms[code]["starting_chips"],
        "bet": 0,
        "status": "waiting",
        "total_invested": 0
    }
    rooms[code]["player_order"].append(sid)
    player_to_room[sid] = code
    join_room(code)
    
    emit('room_joined', {"code": code, "is_host": True})
    broadcast_state(code)

@socketio.on('join_room')
def on_join_room(data):
    sid = request.sid
    name = data.get("name")
    code = data.get("code")
    
    if code not in rooms:
        emit('error', {"msg": "Room not found"})
        return
        
    rooms[code]["players"][sid] = {
        "name": name,
        "chips": rooms[code]["starting_chips"],
        "bet": 0,
        "status": "waiting",
        "total_invested": 0
    }
    rooms[code]["player_order"].append(sid)
    player_to_room[sid] = code
    join_room(code)
    
    emit('room_joined', {"code": code, "is_host": False})
    broadcast_state(code)

# --- GAME LOGIC ---

def advance_turn_if_needed(state):
    start_idx = state["turn_idx"]
    while True:
        if state["turn_idx"] >= len(state["player_order"]):
            state["turn_idx"] = 0
        sid = state["player_order"][state["turn_idx"]]
        p = state["players"][sid]
        if p["status"] == "active":
            break
        state["turn_idx"] = (state["turn_idx"] + 1) % len(state["player_order"])
        if state["turn_idx"] == start_idx:
            break

def check_round_over(state):
    active_players = [p for p in state["players"].values() if p["status"] == "active"]
    not_folded = [p for p in state["players"].values() if p["status"] in ["active", "all-in"]]
    
    if len(not_folded) <= 1:
        state["phase"] = "end"
        return True
        
    for p in active_players:
        if p["bet"] < state["current_bet"]:
            return False
            
    return True

def reset_bets_for_street(state):
    for p in state["players"].values():
        p["bet"] = 0
    state["current_bet"] = 0
    state["min_raise"] = state["blinds"]["bb"]
    state["turn_idx"] = (state["dealer_idx"] + 1) % len(state["player_order"])
    advance_turn_if_needed(state)

@socketio.on('host_action')
def on_host_action(data):
    sid = request.sid
    code = player_to_room.get(sid)
    if not code: return
    state = rooms[code]
    if state["host_sid"] != sid: return
    
    action = data.get("action")
    
    if action == "start_hand":
        if len(state["player_order"]) < 2: return
        state["phase"] = "preflop"
        state["pot"] = 0
        state["current_bet"] = state["blinds"]["bb"]
        state["min_raise"] = state["blinds"]["bb"]
        
        for p in state["players"].values():
            p["status"] = "active" if p["chips"] > 0 else "waiting"
            p["bet"] = 0
            p["total_invested"] = 0

        state["dealer_idx"] = (state["dealer_idx"] + 1) % len(state["player_order"])
        num_players = len([p for p in state["players"].values() if p["status"] == "active"])
        
        sb_idx = (state["dealer_idx"] + 1) % len(state["player_order"])
        bb_idx = (state["dealer_idx"] + 2) % len(state["player_order"])
        if num_players == 2:
            sb_idx = state["dealer_idx"]
            bb_idx = (state["dealer_idx"] + 1) % len(state["player_order"])

        sb_sid = state["player_order"][sb_idx]
        bb_sid = state["player_order"][bb_idx]
        
        def post_blind(s, amount):
            p = state["players"][s]
            actual = min(p["chips"], amount)
            p["chips"] -= actual
            p["bet"] += actual
            p["total_invested"] += actual
            state["pot"] += actual
            if p["chips"] == 0: p["status"] = "all-in"
                
        post_blind(sb_sid, state["blinds"]["sb"])
        post_blind(bb_sid, state["blinds"]["bb"])
        
        state["turn_idx"] = (bb_idx + 1) % len(state["player_order"])
        advance_turn_if_needed(state)
        
    elif action == "next_street":
        if state["phase"] == "preflop": state["phase"] = "flop"
        elif state["phase"] == "flop": state["phase"] = "turn"
        elif state["phase"] == "turn": state["phase"] = "river"
        elif state["phase"] == "river": state["phase"] = "end"
        reset_bets_for_street(state)
        
    elif action == "end_hand":
        state["phase"] = "end"
        
    elif action == "award_pot":
        winners = data.get("winners", [])
        if not winners: return
        participants = [p for p in state["players"].values() if p["total_invested"] > 0]
        participants.sort(key=lambda x: x["total_invested"])
        
        pots = []
        last_invested = 0
        for i, p in enumerate(participants):
            contribution = p["total_invested"] - last_invested
            if contribution > 0:
                pot_size = contribution * len(participants[i:])
                eligible = [wp for wp in participants[i:] if wp["status"] != "folded"]
                pots.append({"size": pot_size, "eligible": eligible})
                last_invested = p["total_invested"]
        
        for pot in pots:
            eligible_sids = [p["name"] for p in pot["eligible"]]
            winning_eligible = [w for w in winners if state["players"][w]["name"] in eligible_sids]
            if winning_eligible:
                split = pot["size"] // len(winning_eligible)
                for w in winning_eligible:
                    state["players"][w]["chips"] += split
            else:
                if pot["eligible"]:
                    split = pot["size"] // len(pot["eligible"])
                    for ep in pot["eligible"]:
                        for s, p_data in state["players"].items():
                            if p_data["name"] == ep["name"]:
                                state["players"][s]["chips"] += split

        state["pot"] = 0
        state["phase"] = "waiting"
        for p in state["players"].values():
            p["status"] = "waiting"
            p["bet"] = 0
            p["total_invested"] = 0

    broadcast_state(code)

@socketio.on('action')
def on_action(data):
    sid = request.sid
    code = player_to_room.get(sid)
    if not code: return
    state = rooms[code]
    
    action = data.get("action")
    amount = int(data.get("amount", 0))
    
    if state["player_order"][state["turn_idx"]] != sid: return
    p = state["players"][sid]
    
    if action == "fold":
        p["status"] = "folded"
    elif action in ["call", "check"]:
        to_call = state["current_bet"] - p["bet"]
        actual = min(p["chips"], to_call)
        p["chips"] -= actual
        p["bet"] += actual
        p["total_invested"] += actual
        state["pot"] += actual
        if p["chips"] == 0: p["status"] = "all-in"
    elif action == "raise":
        total_bet = amount
        add_amount = total_bet - p["bet"]
        actual = min(p["chips"], add_amount)
        p["chips"] -= actual
        p["bet"] += actual
        p["total_invested"] += actual
        state["pot"] += actual
        if p["bet"] > state["current_bet"]:
            state["min_raise"] = p["bet"] - state["current_bet"]
            state["current_bet"] = p["bet"]
        if p["chips"] == 0: p["status"] = "all-in"
            
    state["turn_idx"] = (state["turn_idx"] + 1) % len(state["player_order"])
    advance_turn_if_needed(state)
    
    if check_round_over(state):
        if state["phase"] == "preflop":
            state["phase"] = "flop"
            reset_bets_for_street(state)
        elif state["phase"] == "flop":
            state["phase"] = "turn"
            reset_bets_for_street(state)
        elif state["phase"] == "turn":
            state["phase"] = "river"
            reset_bets_for_street(state)
        elif state["phase"] == "river":
            state["phase"] = "end"
            
    broadcast_state(code)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
