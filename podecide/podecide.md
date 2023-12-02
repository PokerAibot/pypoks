## podecide - Poker Decisions

Podecide folder contains code responsible for making poker decisions using policies. The main objects are:

- **DMK** - Decision MaKer, the top layer of abstraction responsible for learning and making decisions 
- **DMK Module** - PyTorch definition of NN used for learning / storing / and running policy 
- **StatsManager** - a component that provides statistics to support DMK durring learning and decision-making 
- **GamesManager** - manages many DMKs while playing poker games on multiple tables
---

### DMK - Decision MaKer

The Decision MaKer (DMK) defines basic interface for making decisions for poker players (PPlayer on PTable).
A single DMK handles one policy and makes decisions for multiple players (n_players).
Decisions are made using the **Many States One Decision** (MSOD) concept.
MSOD assumes that a table player can send multiple (1-N) states to DMK before asking DMK for a move decision.
DMK computes policy moves probabilities for all the sent states, even for those
that do not require table decisions from a player. 

The two main functions of DMK are:
- receive data from poker players (instances on the tables)
- make decisions (moves) for the players

##### Receiving Data
DMK receives data (Hand History) from a table player. Player sends a list of states (calling: ```DMK.collect_states```)
either before making a move or after a hand. Occasionally, the player sends a list of possible_moves
(calling: ```DMK.collect_possible_moves```). Possible_moves are added by DMK to the last send state.
After sending possible moves, the player/table must wait for DMK's decision:
- no new states from the table (for that player) will be received until a decision is made 
- table with the waiting player is locked at this point

##### Making Decisions
DMK makes decisions (moves) for players. Move is selected based on:
- DMK’s trainable policy
- possible moves sent by the player 
- received states (saved in ```_states_new```)
- any previous history saved by DMK

DMK decides WHEN to make decisions (```DMK.make_decisions```). DMK makes decisions for (one-some-all) players
with allowed_moves saved in ```_states_new```. States used to make decisions are moved (appended)
to ```_states_dec```, from where they are used to update DMK’s policy during training.