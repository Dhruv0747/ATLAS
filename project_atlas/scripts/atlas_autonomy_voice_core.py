"""Spoken autonomy events (2026-11-15, owner: "agar kisi wajah se rukta hai to speaker se bole"). Pure, no ROS.

Turns mux safety text, mission-control status and Nav2 recovery counts into short Hindi sentences for the existing
voice companion (/atlas/voice/test_speak: speech only, never motion). Speaks only while Autonomous mode is ON or an
autonomous goal is running, never repeats the same sentence within REPEAT_S, and keeps GAP_S between sentences.
"""
import re

REPEAT_S = 15.0
GAP_S = 4.0

SAFETY_RULES = [
    (re.compile(r'AUTONOMY BLOCKED: FRONT ULTRASONIC'), 'आगे वाला सेंसर डेटा नहीं दे रहा, इसलिए मैं रुक गया हूँ।'),
    (re.compile(r'AUTONOMY BLOCKED: REAR ULTRASONIC'), 'पीछे वाला सेंसर डेटा नहीं दे रहा, इसलिए मैं रुक गया हूँ।'),
    (re.compile(r'AUTONOMY BLOCKED: FRONT'), 'आगे कुछ बहुत पास है, मैं रुक गया हूँ।'),
    (re.compile(r'AUTONOMY BLOCKED: REAR'), 'पीछे कुछ बहुत पास है, मैं रुक गया हूँ।'),
    (re.compile(r'AUTONOMY BLOCKED: (LEFT|RIGHT)'), 'साइड में कुछ बहुत पास है, मैं रुक गया हूँ।'),
    (re.compile(r'LIDAR AVAILABILITY STOP'), 'लाइडार को रास्ता साफ़ नहीं दिख रहा, मैं रुक गया हूँ।'),
    (re.compile(r'ENCODER|AUTONOMY DEGRADED'), None),        # degraded speed is normal with M3 excluded: stay quiet
    (re.compile(r'LOCALIZATION|localization'), 'मुझे अपनी जगह पक्की नहीं पता, इसलिए रुक गया हूँ।'),
]

MISSION_RULES = [
    (re.compile(r'NAMED GOAL ACCEPTED name=map point'), 'ठीक है, वहाँ जा रहा हूँ।'),
    (re.compile(r'NAMED GOAL ACCEPTED name=(.+)'), lambda m: f'ठीक है, {m.group(1)} की तरफ़ जा रहा हूँ।'),
    (re.compile(r'NAMED GOAL FINISHED .*status=4'), 'मैं पहुँच गया।'),
    (re.compile(r'NAMED GOAL FINISHED .*status=5'), 'रुक गया।'),
    (re.compile(r'NAMED GOAL FINISHED .*status=6'), 'मुझे वहाँ तक रास्ता नहीं मिला, मैं रुक गया हूँ।'),
    (re.compile(r'NAMED GOAL REJECTED'), 'नेविगेशन ने यह जगह मना कर दी।'),
    (re.compile(r'NAVIGATION STOPPED: camera obstacles lost'), 'कैमरा बंद हो गया, इसलिए मैं रुक गया हूँ।'),
    (re.compile(r'ERROR .*too close to a wall'), 'वह जगह दीवार के बहुत पास है, वहाँ नहीं जा सकता।'),
    (re.compile(r'ERROR .*(unknown|occupied) on the map'), 'वह जगह मैप पर खाली नहीं है।'),
    (re.compile(r'ERROR .*camera obstacles OFF'), 'कैमरा चालू नहीं है, इसलिए नहीं चल सकता।'),
    (re.compile(r'ERROR .*localization'), 'मुझे अपनी जगह पक्की नहीं पता, इसलिए नहीं चल सकता।'),
    (re.compile(r'ERROR (navigate|save)'), 'यह काम नहीं हो पाया।'),
]


def _match(rules, text):
    for rx, out in rules:
        m = rx.search(text or '')
        if m:
            return out(m) if callable(out) else out, True
    return None, False


class AutonomyVoice:
    def __init__(self):
        self.armed = False
        self.goal_active = False
        self.last_said = {}
        self.last_any = -1e9
        self.recoveries = 0
        self.prev_armed = None
        self.prev_latched = None

    def _say(self, sentence, now):
        if not sentence:
            return None
        if now - self.last_said.get(sentence, -1e9) < REPEAT_S or now - self.last_any < GAP_S:
            return None
        self.last_said[sentence] = now
        self.last_any = now
        return sentence

    def on_policy(self, policy, now):
        auto = (policy or {}).get('autonomy') or {}
        armed, latched = bool(auto.get('armed')), bool((policy or {}).get('stop_latched'))
        out = None
        if self.prev_armed is not None and armed != self.prev_armed:
            out = self._say('ऑटोनॉमस मोड चालू।' if armed else 'मैनुअल मोड।', now)
        elif (self.prev_latched is False and latched and (self.armed or self.goal_active)):
            out = self._say('इमरजेंसी स्टॉप। मैं रुक गया हूँ।', now)
        self.armed, self.prev_armed, self.prev_latched = armed, armed, latched
        return out

    def on_safety(self, text, now):
        if not (self.armed or self.goal_active):
            return None
        sentence, matched = _match(SAFETY_RULES, text)
        return self._say(sentence, now) if matched else None

    def on_mission(self, text, now):
        if 'NAMED GOAL ACCEPTED' in (text or ''):
            self.goal_active, self.recoveries = True, 0
        sentence, matched = _match(MISSION_RULES, text)
        if 'NAMED GOAL FINISHED' in (text or '') or 'NAVIGATION STOPPED' in (text or ''):
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
        return self._say('रास्ते में कुछ है, मैं नया रास्ता ढूँढ रहा हूँ।', now)
