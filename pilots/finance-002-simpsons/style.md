# Style rules — Simpsons-style finance channel

## Look (matches Nick Invests, our own character)
- Our own Simpsons-style everyman: yellow skin, big round white eyes, small black pupils, slight overbite,
  four-finger hands, neat brown hair with a cowlick, light blue crew-neck t-shirt, dark jeans, white sneakers.
- **Pure white background** with only faint line-art props. Good things glow **green**, bad things glow **red**.
- **Still pictures only.** No talking, no animation, no zoom, no pans. Hold each picture, cut on the narration.
- No text, letters or numbers in pictures (captions are added in the edit).

## Eyes — the rule that keeps the face from breaking
- **Both eyes are always in the same state.** Never one open and one half-closed.
- **Closed eyes** (asleep, blissful, wincing): drawn as **two short downward curved lines, with no white
  eyeballs and no pupils**. Use exactly that wording in every prompt that needs closed eyes.
- **Closed eyes are made with an eye-only EDIT, never drawn from scratch.** Tested 2026-10-13: generating
  "eyes closed" failed 5 of 6 times (the model keeps the round eyeballs); editing only the eyes
  ("erase the eyeballs and pupils, draw each eye as one short downward curved line, keep everything else")
  worked 5 of 6. Turned-away sleeping poses came out distorted, so don't use them.
- For any expression that is in the expression sheet, **use the approved sheet image as the reference**
  instead of describing the face in words.

## Expression sheet (approved references in characters/)
neutral · happy · worried · panicked · relieved · asleep
