#!/usr/bin/env python3
"""Offline footprint-aware connectivity check for a ROS PGM occupancy map."""
import argparse
from collections import deque
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument("image")
p.add_argument("--origin", nargs=2, type=float, required=True)
p.add_argument("--resolution", type=float, required=True)
p.add_argument("--start", nargs=2, type=float, required=True)
p.add_argument("--goal", nargs=2, type=float, required=True)
p.add_argument("--inflate-cells", type=int, default=4)
a = p.parse_args()
im = Image.open(a.image).convert("L")
w, h = im.size
px = im.load()
blocked = {(x, y) for y in range(h) for x in range(w) if px[x, y] < 250}
inflated = set(blocked)
for x, y in blocked:
    for dy in range(-a.inflate_cells, a.inflate_cells + 1):
        for dx in range(-a.inflate_cells, a.inflate_cells + 1):
            if dx * dx + dy * dy <= a.inflate_cells * a.inflate_cells:
                q = (x + dx, y + dy)
                if 0 <= q[0] < w and 0 <= q[1] < h:
                    inflated.add(q)

def cell(world):
    return (round((world[0] - a.origin[0]) / a.resolution),
            h - 1 - round((world[1] - a.origin[1]) / a.resolution))

def nearest_free(seed):
    if seed not in inflated:
        return seed
    for radius in range(1, 21):
        candidates = [(seed[0] + dx, seed[1] + dy)
                      for dy in range(-radius, radius + 1)
                      for dx in range(-radius, radius + 1)
                      if abs(dx) == radius or abs(dy) == radius]
        candidates = [q for q in candidates
                      if 0 <= q[0] < w and 0 <= q[1] < h and q not in inflated]
        if candidates:
            return min(candidates, key=lambda q: (q[0]-seed[0])**2+(q[1]-seed[1])**2)
    return None

start_raw, goal_raw = cell(a.start), cell(a.goal)
start, goal = nearest_free(start_raw), nearest_free(goal_raw)
seen = set()
if start:
    todo = deque([start]); seen.add(start)
    while todo:
        x, y = todo.popleft()
        for q in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0 <= q[0] < w and 0 <= q[1] < h and q not in inflated and q not in seen:
                seen.add(q); todo.append(q)
print({"size_cells": [w,h], "size_m": [w*a.resolution,h*a.resolution],
       "start_raw": start_raw, "start_free": start, "goal_raw": goal_raw,
       "goal_free": goal, "connected": bool(goal and goal in seen),
       "reachable_cells": len(seen), "inflation_m": a.inflate_cells*a.resolution})
