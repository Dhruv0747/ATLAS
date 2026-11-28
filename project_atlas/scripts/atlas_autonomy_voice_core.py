"""Spoken autonomy events (2026-11-15, owner: "agar kisi wajah se rukta hai to speaker se bole"). Pure, no ROS.

Turns mux safety text, mission-control status and Nav2 recovery counts into short Hindi sentences for the existing
voice companion (/atlas/voice/test_speak: speech only, never motion). Mode changes, E-STOP and the goal's own start /
end are always spoken; obstacle/safety reasons only WHILE a goal is running (2026-11-16 owner: "after it stops it keeps
talking"), never repeating the same REASON within REPEAT_S, and keeping GAP_S between sentences.

2026-11-28 (owner: "I need the exact reason spoken, not one or two recordings, easy to understand"): every sentence
says the exact reason (side and distance, which sensor, which kind of localisation problem, which refusal) and what to
do. Repeat suppression is keyed by the reason, not by the sentence, so a changing distance does not make ATLAS talk
every few seconds. A refusal nobody has a rule for says that the reason is on the dashboard ("Why" card), never just
"it could not be done".
"""
import re

REPEAT_S = 45.0          # 2026-11-16: 15 s repeated the same stop reason too often
GAP_S = 4.0

# 2026-11-28 owner: numbers as English words ("eighteen", not "atharah"), "left" / "right", and Hinglish, not pure
# Hindi: Hindi grammar with the everyday English words (path, sensor, location, wall, goal, remote, map, camera).
SIDE = {'FRONT': 'Front में', 'REAR': 'Back में', 'LEFT': 'Left side में', 'RIGHT': 'Right side में'}
SENSOR_SIDE = {'FRONT': 'Front', 'REAR': 'Back', 'LEFT': 'Left', 'RIGHT': 'Right'}
_ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve',
         'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']
_TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']


def number_words(n):
    """0..999 as English words, so the Hindi voice says "eighteen" instead of reading digits in Hindi."""
    n = int(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ('' if n % 10 == 0 else ' ' + _ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + ' hundred' + ('' if rest == 0 else ' ' + number_words(rest))
    return str(n)


def _cm(metres):
    try:
        cm = int(round(float(metres) * 100))
    except (TypeError, ValueError):
        return 'बहुत पास'
    return number_words(cm) + ' centimeter' if 0 <= cm < 1000 else 'बहुत पास'


def _ultrasonic(m):
    side = SENSOR_SIDE.get(m.group(1), '')
    return ('%s ultrasonic sensor data नहीं दे रहा, इसलिए मैं रुक गया हूँ। उसका wire check कीजिए।' % side).strip()


def _blocked(m):
    side = SIDE[m.group(1)]
    where = '%s %s पर कुछ है' % (side, _cm(m.group(2))) if m.group(2) else '%s कुछ बहुत पास है' % side
    return where + ', इसलिए मैं रुक गया हूँ। Path clear होते ही खुद चलूँगा।'


# (pattern, sentence or function(match), repeat key). First match wins: more specific first. key None = say nothing.
SAFETY_RULES = [
    (re.compile(r'AUTONOMY BLOCKED: (FRONT|REAR|LEFT|RIGHT) ULTRASONIC'), _ultrasonic, 'ultrasonic'),
    (re.compile(r'INVALID ULTRASONIC'),
     'Ultrasonic sensor का data गड़बड़ है, इसलिए मैं रुक गया हूँ। Sensor check कीजिए।', 'ultrasonic'),
    (re.compile(r'AUTONOMY BLOCKED: (FRONT|REAR|LEFT|RIGHT)\b(?: ([\d.]+) ?m)?'), _blocked, 'blocked'),
    (re.compile(r'LIDAR AVAILABILITY'),
     'LiDAR को मेरे path का कुछ हिस्सा नहीं दिख रहा, इसलिए मैं रुक गया हूँ। Path के पास की black, shiny '
     'या open जगह cover कीजिए या हटाइए।', 'lidar'),
    (re.compile(r'LOCALIZATION JUMP'),
     'मेरी location अचानक बदल गई, इसलिए मैं रुक गया हूँ। कुछ seconds रुकिए, मैं location फिर से confirm करूँगा।', 'loc'),
    (re.compile(r'LOCALIZATION STALE'),
     'मेरी location की जानकारी पुरानी हो गई है, इसलिए मैं रुक गया हूँ। Find my location चलाइए।', 'loc'),
    (re.compile(r'LOCALIZATION|localization'),
     'मुझे map पर अपनी location पक्की नहीं पता, इसलिए मैं रुक गया हूँ। कुछ seconds रुकिए या Find my location चलाइए।',
     'loc'),
    (re.compile(r'AUTONOMY STOP: ENCODER'),
     'Wheel sensors पर अभी भरोसा नहीं है, इसलिए मैं रुक गया हूँ। मुझे थोड़ी देर खड़ा रहने दीजिए।', 'encoder'),
    (re.compile(r'RADAR LIMIT'), 'पास में कोई person या moving चीज़ है, इसलिए मैं slow चल रहा हूँ।', 'radar'),
    (re.compile(r'ENCODER|AUTONOMY DEGRADED'), None, None),   # degraded speed is normal with M3 excluded: stay quiet
]

_UNKNOWN_REFUSAL = 'यह काम नहीं हो पाया। सही reason dashboard पर Why card में लिखा है।'
MISSION_RULES = [
    (re.compile(r'NAMED GOAL ACCEPTED name=map point'), 'Ok, वहाँ जा रहा हूँ।'),
    (re.compile(r'NAMED GOAL ACCEPTED name=(.+)'), lambda m: f'Ok, {m.group(1)} की तरफ़ जा रहा हूँ।'),
    (re.compile(r'NAMED GOAL FINISHED name=map point.*status=4'), 'मैं पहुँच गया।'),
    (re.compile(r'NAMED GOAL FINISHED name=(.+?) status=4'), lambda m: f'मैं {m.group(1)} पहुँच गया।'),
    (re.compile(r'NAMED GOAL FINISHED .*status=5'), 'Goal cancel हुआ, मैं रुक गया हूँ।'),
    (re.compile(r'NAMED GOAL FINISHED name=map point.*status=6'),
     'मुझे वहाँ तक path नहीं मिला, मैं रुक गया हूँ। Path clear कीजिए या पास की जगह चुनिए।'),
    (re.compile(r'NAMED GOAL FINISHED name=(.+?) status=6'),
     lambda m: f'मुझे {m.group(1)} तक path नहीं मिला, मैं रुक गया हूँ। Path clear कीजिए या पास की जगह चुनिए।'),
    (re.compile(r'NAMED GOAL REJECTED'), 'Navigation ने यह goal reject कर दिया। दूसरी जगह चुनिए।'),
    (re.compile(r'NAVIGATION CANCELED'), 'Mission cancel। मैं रुक गया हूँ।'),
    (re.compile(r'NAVIGATION STOPPED: camera obstacles lost'),
     'Camera बंद हो गया, इसलिए मैं रुक गया हूँ। Depth camera on कीजिए।'),
    (re.compile(r'BUSY: ignored'), 'मैं अभी दूसरा काम कर रहा हूँ, इसलिए यह command छोड़ दिया। थोड़ी देर बाद फिर से दीजिए।'),
    (re.compile(r'ERROR .*(current pose is not in known clear space|candidate start is not clear)'),
     'मैं खुद wall या furniture के बहुत पास खड़ा हूँ, इसलिए goal start नहीं किया। मुझे remote से open जगह में ले जाइए।'),
    (re.compile(r'ERROR .*(too close to a wall|occupied within|unknown within|(unknown|occupied) on the map)'),
     'वह जगह wall या किसी चीज़ के बहुत पास है, वहाँ नहीं जा सकता। Room की open जगह चुनिए।'),
    (re.compile(r'ERROR .*camera obstacles OFF'), 'Camera on नहीं है, इसलिए नहीं चल सकता। Depth camera on कीजिए।'),
    (re.compile(r'ERROR .*[Ll]ocali[sz]ation'),
     'मुझे अपनी location पक्की नहीं पता, इसलिए नहीं चल सकता। Find my location चलाइए।'),
    (re.compile(r'ERROR .*(scan|SCAN).*(agree|match|fit)'),
     'LiDAR का view map से match नहीं हो रहा, इसलिए नहीं चल सकता। Find my location चलाइए।'),
    (re.compile(r'ERROR (navigate|save)'), _UNKNOWN_REFUSAL),
]


def _match(rules, text):
    for rx, out in rules:
        m = rx.search(text or '')
        if m:
            return out(m) if callable(out) else out, True
    return None, False


def _match_keyed(rules, text):
    for rx, out, key in rules:
        m = rx.search(text or '')
        if m:
            return (out(m) if callable(out) else out), key, True
    return None, None, False


class AutonomyVoice:
    def __init__(self):
        self.armed = False
        self.goal_active = False
        self.last_said = {}
        self.last_any = -1e9
        self.recoveries = 0
        self.prev_armed = None
        self.prev_latched = None

    def _say(self, sentence, now, key=None):
        if not sentence:
            return None
        key = key or sentence
        if now - self.last_said.get(key, -1e9) < REPEAT_S or now - self.last_any < GAP_S:
            return None
        self.last_said[key] = now
        self.last_any = now
        return sentence

    def on_policy(self, policy, now):
        auto = (policy or {}).get('autonomy') or {}
        armed, latched = bool(auto.get('armed')), bool((policy or {}).get('stop_latched'))
        out = None
        if self.prev_armed is not None and armed != self.prev_armed:
            out = self._say('Autonomous mode on।' if armed else 'Manual mode।', now)
        elif (self.prev_latched is False and latched and (self.armed or self.goal_active)):
            out = self._say('Emergency stop। मैं रुक गया हूँ। चलाने के लिए remote से stop release कीजिए।', now)
        self.armed, self.prev_armed, self.prev_latched = armed, armed, latched
        return out

    def on_safety(self, text, now):
        if not self.goal_active:
            return None
        sentence, key, matched = _match_keyed(SAFETY_RULES, text)
        return self._say(sentence, now, key) if matched else None

    def on_mission(self, text, now):
        if 'NAMED GOAL ACCEPTED' in (text or ''):
            self.goal_active, self.recoveries = True, 0
        sentence, matched = _match(MISSION_RULES, text)
        if any(k in (text or '') for k in ('NAMED GOAL FINISHED', 'NAVIGATION STOPPED', 'NAVIGATION CANCELED')):
            self.goal_active = False
        if not matched:
            return None
        return self._say(sentence, now)

    def on_recoveries(self, count, now):
        """Nav2 NavigateToPose feedback number_of_recoveries: each new recovery = blocked path, replanning."""
        if not self.goal_active or count <= self.recoveries:
            self.recoveries = max(self.recoveries, count) if self.goal_active else 0
            return None
        self.recoveries = count
        return self._say('Path में कुछ है, मैं नया path ढूँढ रहा हूँ।', now)
