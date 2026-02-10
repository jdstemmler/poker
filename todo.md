# TODO list for feature enhancements / roadmap, bug fixes, and overall gameplay improvements

## BUGS
* when entering a numeric value on the game creation screen, leading zero stays in the field for those inputs where the default is 0. For example, entering a blind duration of 20 minutes shows up as 020 but the field is correctly parsed.

* Changing a numeric field requires clicking into the field and then deleting the values that are in there, then putting new values in. Clicking in the field should clear the existing values - maybe have placeholder values in there representing the defaults that would clear when you click in the box?

## Feature Roadmap

## General Useability Enhancements
* player feedback has indicated that the pin code is confusing. Joining players though that they needed a pin from the game creator to join the game, instead of it being a pin set by the player. This is explained in the help modal, but could be clearer on the registration page.

* players should have the option to exit the lobby, removing their player from the game. This would take them back to the registration page for the game.

* "Game Won" screen at the end appears too fast and blocks the previous hand. There's no way to see what the winning hand was, it just shows the winner of the game. Maybe instead of showing a modal over the table, we replace the player list with the winner and rankings?

* I'm not sure we need a max player field in the game settings. Given that this is for casual friends gameplay, there's not really a need to limit this. Maybe we would limit it to 50 players on the backend just to avoid some scenario where someone spams the game server.

* add an option to see the blind schedule (at least out to the first 10 blinds or something) as well as a selector for the multiplier. I don't know how the blind schedule is currently determined, but maybe an option to do a 1x increment (10, 20, 30, 40), a 2x increment (10, 20, 40, 80...) and some values in-between (1.5x? 1.2x? not sure what common poker blind schedules are or how much they vary)

* add a checkbox on the game creation screen to enable or disable auto deal next hand

* organize the game settings more logically. Blind settings should be grouped together, turn timer and auto deal should be together, rebuy options all together.

* user feedback indicates that the Check / Call button switching has inadvertently led to situations where they accidentally called when they thought they were checking because the button changed while in the same location. Need to add a little bit of friction to the call action to make it more obvious. Maybe a full-width button above the Fold/Check/Raise buttons, similar to where the raise options are, would appear when calling is the only option and we could disable the check button?