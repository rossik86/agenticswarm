# Town Layout Guide

Town view uses a compact star layout.

- `Main CO` stays in the visual center and acts as the command node.
- Work rooms are placed around `Main CO` as a six-point star: analyst, supervisor, researcher, learner, builder, reviewer.
- Room cards should stay compact enough to leave clear space for flow edges and checkpoint labels.
- Agent sprites should remain smaller than room furniture, so they read as participants inside the room instead of covering the room art.
- Desktop and tablet layouts keep the star shape. Mobile uses a vertical fallback because the star layout becomes too dense on narrow screens.
- Flow positions in `frontend/src/main.jsx` and card sizes in `frontend/src/styles.css` must be updated together because React Flow positions are centered by fixed node offsets.
