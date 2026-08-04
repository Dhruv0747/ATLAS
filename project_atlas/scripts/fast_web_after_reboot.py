from pathlib import Path

p = Path("/home/jetson/project_atlas/scripts/atlas_status_web.py")
s = p.read_text()
start = s.index("def gps_status():")
end = s.index("\ndef snapshot():", start)
replacement = '''def gps_status():
    # Keep page loading fast after reboot. Full GPS detail is on the 7-inch dashboard.
    return {"satellites": "--", "constellations": "open dashboard"}
'''
s = s[:start] + replacement + s[end + 1:]
p.write_text(s)
