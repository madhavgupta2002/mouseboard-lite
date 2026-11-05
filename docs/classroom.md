# A five-minute classroom walkthrough

## 1. The idea

The phone is a sensor and a touch controller. The computer is the receiver.
The phone runs an ordinary webpage; Python performs the operating-system actions.

```text
Phone orientation / touch / keyboard
                 ↓
         web/app.js + motion.mjs
                 ↓
   authenticated WebSocket over local Wi-Fi
                 ↓
              server.py
                 ↓
          input_control.py
                 ↓
       desktop cursor / keyboard
```

## 2. Walk through one click

1. `pointerdown` on the Left button sends:

   ```json
   {"type": "button", "button": "left", "down": true}
   ```

2. `server.py` reads the JSON on its WebSocket.
3. `input_control.py` validates the fields and calls `mouseDown(button="left")`.
4. `pointerup` sends the same message with `down: false`.
5. Holding the button while moving sends drag movement naturally: the desktop
   still considers the left mouse button pressed.

Pointer capture keeps the release event connected to the button even if the
finger slides outside it. A three-second connection timeout handles a sleeping
or disconnected phone.

## 3. Walk through motion

The browser supplies three orientation angles:

- **alpha:** rotation around the screen's normal axis;
- **beta:** front/back tilt;
- **gamma:** left/right tilt.

Simply subtracting angle values fails at wraparound and when the browser changes
Euler-angle representation. `motion.mjs` converts them into a quaternion, a
four-number rotation representation.

The first reading after Recenter becomes the neutral rotation. Each new reading
is compared with it:

```text
relative rotation = inverse(neutral rotation) × current rotation
```

The code extracts horizontal rotation and vertical pitch from that relative
rotation. Each axis is smoothed independently. Movement smaller than the dead
zone is held until enough intentional motion accumulates.

```text
pixels moved = change in filtered angle × sensitivity
```

The browser batches fractional pixels into one message per animation frame.
A slow deliberate turn still accumulates enough motion to move the pointer.
Huge jumps and stale samples reset the filter instead of making the cursor jump.

## 4. Walk through typing

Tapping the textarea opens the phone's normal keyboard. The page compares the
previous text with the new text and sends the changed suffix:

```text
old: "teh"      new: "the "
common prefix: "t"
delete 2 characters, then type "he "
```

This supports autocorrect without repeatedly typing the whole sentence.
Composition events wait for the phone keyboard to finish choosing its text.
The supported desktop layout is English/US; arbitrary Unicode is outside this MVP.

## 5. Explain why HTTPS and pairing exist

- Browsers require a secure context for orientation sensors.
- For a classroom-only HTTP demo, Chrome can treat one explicitly allowed local
  address as secure using a development flag. This removes certificate setup,
  but does not encrypt traffic. Reset the flag after the demo.
- A local certificate authority lets the phone trust the local HTTPS server.
  It is generated on this computer, and its private key never goes to the phone.
- The certificate setup page carries no control commands.
- The pairing QR contains a random code. The page sends it during the secure
  WebSocket handshake; the server also checks the webpage's origin.
- One connection controls the computer at a time, and only a small list of
  mouse/keyboard commands is accepted.

## Demo order

1. Start Python and open the phone controller.
2. Connect, hold the phone screen-up, and Recenter.
3. Move horizontally, then vertically.
4. Click, hold and drag, then scroll.
5. Type a sentence; show a corrected word.
6. Switch away from the phone page to show that a drag is released.
7. Run the tests: the fake desktop records actions without touching the real cursor.
