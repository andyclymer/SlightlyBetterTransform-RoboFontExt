# Slightly Better Transform, RoboFont Extension

*Work in progress!*

Transform the selection with fewer features than RoboFont's built-in transform, but with some small improvements:
        
- Points only round once, you're free to continue transforming the selection without accumulating rounding errors
- You can select the transform "handles" and use the arrow keys to nudge them around
- With no handles selected, dragging and nudging will move the selection
- Shows deltas for how far each face of the transform bounding box moved
- The transformation bounding box excludes the off-curves, making it easier to measure how far the on-curves moved
- Command-shift-R activates and deactivates the tool

Built for Python 3 and RoboFont 3.1
