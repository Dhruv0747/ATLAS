#!/usr/bin/env python3
"""Project ATLAS bilingual USB voice companion.

ESP32 protocol: packed little-endian <IBBHI, magic ATLS.
Locomotion requests use a two-step confirmation gate and short, bounded
velocity pulses through the existing watchdog-protected WEB mux channel.
"""

import audioop
import hashlib
import io
import json
import math
import os
import queue
import re
import struct
import subprocess
import threading
import time
import wave

import requests
import serial

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool, Empty, Float32, Int32, String


MAGIC = 0x534C5441
HEADER = struct.Struct("<IBBHI")
MIC_PCM, EVENT, PLAY_PCM, STATE = 1, 2, 0x81, 0x82
PLAY_BEGIN, PLAY_END = 0x83, 0x84
DEVICE = os.getenv(
    "ATLAS_VOICE_DEVICE",
    "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_28:84:85:57:02:24-if00",
)
API_BASE = "https://api.openai.com/v1"
SAMPLE_RATE = 16000
PLAY_CHUNK_BYTES = 60000


class AtlasVoice(Node):
    def __init__(self):
        super().__init__("atlas_voice_companion")
        self.pubs = {
            name: self.create_publisher(String, f"/atlas/voice/{name}", 10)
            for name in (
                "state", "mode", "transcript", "intent", "action",
                "response", "confirmation", "rgb", "cloud",
            )
        }
        self.last_values = {}
        self.rover = {}
        self.conversation = []
        # Physical forward/default calibration confirmed by Dhruv on 2026-08-02.
        self.pan_us = 1300
        self.tilt_us = 2100
        self.pan_feedback_at = 0.0
        self.tilt_feedback_at = 0.0
        self.speech_lock = threading.Lock()
        self.pan_pub = self.create_publisher(
            Int32, "/camera/bottom_servo_cmd_us", 10
        )
        self.tilt_pub = self.create_publisher(
            Int32, "/camera/second_servo_cmd_us", 10
        )
        self.ai_pub = self.create_publisher(Bool, "/atlas/ai_enabled", 10)
        self.tracker_pub = self.create_publisher(Bool, "/atlas/camera_tracking/enabled", 10)
        self.follow_pub = self.create_publisher(Bool, "/atlas/follow_person/enabled", 10)
        self.agent_pubs = {
            "start_exploration": self.create_publisher(
                Empty, "/atlas/start_exploration", 10
            ),
            "stop_exploration": self.create_publisher(
                Empty, "/atlas/stop_exploration", 10
            ),
            "set_home": self.create_publisher(Empty, "/atlas/set_home", 10),
            "return_home": self.create_publisher(
                Empty, "/atlas/return_home", 10
            ),
        }
        self.pending_agent_action = None
        self.pending_agent_deadline = 0.0
        # This publisher is used only to send a zero-velocity shutdown stop.
        self.stop_pub = self.create_publisher(Twist, "/cmd_vel_joy", 10)
        self.voice_drive_pub = self.create_publisher(Twist, "/cmd_vel_web", 10)
        self.create_subscription(
            Int32, "/camera/bottom_servo_us",
            self.pan_feedback_callback, 10,
        )
        self.create_subscription(
            Int32, "/camera/second_servo_us",
            self.tilt_feedback_callback, 10,
        )
        self.heartbeat = self.create_timer(5.0, self.publish_heartbeat)
        self.create_subscription(
            String, "/atlas/voice/test_speak", self.test_speak_callback, 10
        )
        for topic, key in (
            ("/battery/voltage", "battery_voltage"),
            ("/battery/current", "battery_current"),
            ("/battery/percent", "battery_percent"),
            ("/bms/voltage", "bms_voltage"),
            ("/bms/current", "bms_current"),
            ("/bms/percent", "bms_percent"),
            ("/bms/power", "bms_power"),
            ("/environment/outside_temperature_c", "outside_temperature_c"),
            ("/gps/satellites", "gps_satellites"),
            ("/gps/hdop", "gps_hdop"),
            ("/cellular/signal_percent", "cellular_signal_percent"),
            ("/ultrasonic/front_mm", "ultrasonic_front_mm"),
            ("/ultrasonic/left_mm", "ultrasonic_left_mm"),
            ("/ultrasonic/right_mm", "ultrasonic_right_mm"),
        ):
            self.create_subscription(
                Float32, topic,
                lambda msg, field=key: self.rover.__setitem__(field, msg.data),
                10,
            )
        for topic, key in (
            ("/atlas/health", "health"),
            ("/atlas/readiness", "readiness"),
            ("/atlas/sensor_freshness", "sensor_freshness"),
            ("/atlas/recovery_status", "recovery_status"),
            ("/atlas/recovery_state", "recovery_state"),
            ("/gps/constellations", "gps_constellations"),
            ("/bms/status", "bms_status"),
            ("/cellular/access_tech", "cellular_access"),
            ("/cellular/operator", "cellular_operator"),
            ("/camera/detections/json", "camera_detections"),
            ("/camera/faces/json", "camera_faces"),
            ("/atlas/camera_tracking/status", "camera_tracking_status"),
        ):
            self.create_subscription(
                String, topic,
                lambda msg, field=key: self.rover.__setitem__(field, msg.data),
                10,
            )
        self.create_subscription(NavSatFix, "/gps/fix", self.gps_callback, 10)
        self.serial = None
        self.serial_lock = threading.Lock()
        self.running = True
        self.audio_q = queue.Queue(maxsize=300)
        self.noise_floor = 180.0
        self.calibrate_until = time.monotonic() + 3.0
        self.ignore_mic_until = 0.0
        self.awake_until = 0.0
        self.publish("mode", "AUTO ENGLISH + HINDI")
        self.publish("state", "STARTING")
        self.publish("confirmation", "Motion commands require confirmation")
        self.worker = threading.Thread(target=self.voice_loop, daemon=True)
        self.reader = threading.Thread(target=self.serial_loop, daemon=True)
        self.worker.start()
        self.reader.start()

    @staticmethod
    def time_greeting():
        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            return "Good morning Dhruv. ATLAS is online, safe, and ready to work."
        if 12 <= hour < 17:
            return "Good afternoon Dhruv. ATLAS is online, safe, and ready to work."
        if 17 <= hour < 22:
            return "Good evening Dhruv. ATLAS is online, safe, and ready to work."
        return "Good night Dhruv. ATLAS is online, safe, and ready to work."

    def announce_ready(self):
        # Give ROS, the USB speaker and safety topics time to become available.
        time.sleep(10)
        if not self.running:
            return
        with self.speech_lock:
            try:
                greeting = self.time_greeting()
                self.publish("response", greeting)
                self.publish("action", "ATLAS READY")
                self.play(self.local_speech(greeting))
                self.publish("action", "NONE")
                self.set_state("IDLE")
            except Exception as exc:
                self.publish("cloud", f"STARTUP GREETING ERROR: {exc}")

    def safe_shutdown(self):
        """Key 2 long-press handler: stop first, announce, then power down."""
        if not self.speech_lock.acquire(blocking=False):
            return
        try:
            self.publish("intent", "SAFE SHUTDOWN")
            self.publish("action", "STOPPING ROVER - KEY 2")
            stop = Twist()
            for _ in range(3):
                self.stop_pub.publish(stop)
                time.sleep(0.1)
            text = "Dhruv, ATLAS is shutting down safely. Please wait before removing power."
            self.publish("response", text)
            self.play(self.local_speech(text))
            self.publish("action", "SHUTDOWN REQUESTED")
            result = subprocess.run(
                ["/usr/bin/sudo", "-n", "/sbin/shutdown", "-h", "now"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                self.publish("action", "SHUTDOWN BLOCKED - SUDO RULE REQUIRED")
                self.publish("cloud", result.stderr.strip() or "shutdown permission denied")
        except Exception as exc:
            self.publish("cloud", f"SHUTDOWN ERROR: {exc}")
        finally:
            self.speech_lock.release()

    def handle_esp_event(self, event):
        self.get_logger().info("ESP32: " + event)
        if event == "KEY2_LONG":
            threading.Thread(target=self.safe_shutdown, daemon=True).start()

    def publish(self, name, text):
        self.last_values[name] = str(text)
        msg = String()
        msg.data = str(text)
        self.pubs[name].publish(msg)
        self.get_logger().info(f"{name}: {text}")

    def publish_heartbeat(self):
        """Refresh status for dashboards opened after this node started."""
        for name in ("state", "mode", "confirmation", "rgb", "cloud"):
            if name in self.last_values:
                msg = String()
                msg.data = self.last_values[name]
                self.pubs[name].publish(msg)

    def test_speak_callback(self, msg):
        """Safe diagnostic path: speech only, never locomotion."""
        if not msg.data.strip() or self.speech_lock.locked():
            return
        threading.Thread(
            target=self.run_test_speech, args=(msg.data.strip(),), daemon=True
        ).start()

    def run_test_speech(self, text):
        with self.speech_lock:
            try:
                self.publish("response", text)
                self.play(self.local_speech(text))
                self.set_state("IDLE")
            except Exception as exc:
                self.publish("cloud", f"AUDIO TEST ERROR: {exc}")
                self.set_state("ERROR")
                time.sleep(1)
                self.set_state("IDLE")

    def send_packet(self, packet_type, payload=b""):
        if not self.serial or not self.serial.is_open:
            return False
        try:
            with self.serial_lock:
                self.serial.write(
                    HEADER.pack(MAGIC, packet_type, 0, len(payload), 0) + payload
                )
            return True
        except (OSError, serial.SerialException):
            return False

    def set_state(self, state):
        rgb = {
            "IDLE": "BLUE", "LISTENING": "GREEN", "THINKING": "WHITE",
            "SPEAKING": "BLUE PULSE", "ERROR": "RED",
        }.get(state, state)
        self.publish("state", state)
        self.publish("rgb", rgb)
        self.send_packet(STATE, f"STATE {state}".encode())

    def read_exact(self, count):
        data = bytearray()
        while self.running and len(data) < count:
            chunk = self.serial.read(count - len(data))
            if chunk:
                data.extend(chunk)
        return bytes(data)

    def serial_loop(self):
        while self.running:
            try:
                self.serial = serial.Serial(
                    DEVICE, 921600, timeout=1, write_timeout=2
                )
                self.publish("cloud", "USB ONLINE")
                self.set_state("IDLE")
                threading.Thread(target=self.announce_ready, daemon=True).start()
                while self.running:
                    raw = self.read_exact(HEADER.size)
                    if len(raw) != HEADER.size:
                        continue
                    magic, packet_type, _flags, length, _seq = HEADER.unpack(raw)
                    if magic != MAGIC or length > 8192:
                        self.serial.reset_input_buffer()
                        continue
                    payload = self.read_exact(length)
                    if packet_type == MIC_PCM:
                        try:
                            self.audio_q.put_nowait(payload)
                        except queue.Full:
                            self.audio_q.get_nowait()
                            self.audio_q.put_nowait(payload)
                    elif packet_type == EVENT:
                        self.handle_esp_event(payload.decode(errors="replace"))
            except Exception as exc:
                if not self.running:
                    break
                self.publish("cloud", f"USB OFFLINE: {exc}")
                self.publish("state", "ERROR")
                self.publish("rgb", "RED")
                try:
                    if self.serial:
                        self.serial.close()
                except Exception:
                    pass
                time.sleep(2)

    @staticmethod
    def wav_bytes(pcm):
        output = io.BytesIO()
        with wave.open(output, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SAMPLE_RATE)
            out.writeframes(pcm)
        return output.getvalue()

    def api_headers(self):
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        return {"Authorization": f"Bearer {key}"}

    def gps_callback(self, msg):
        self.rover["gps_status"] = msg.status.status
        if (
            msg.status.status >= 0
            and math.isfinite(msg.latitude)
            and math.isfinite(msg.longitude)
            and (abs(msg.latitude) > 0.001 or abs(msg.longitude) > 0.001)
        ):
            self.rover["latitude"] = msg.latitude
            self.rover["longitude"] = msg.longitude

    def pan_feedback_callback(self, msg):
        self.pan_us = int(msg.data)
        self.pan_feedback_at = time.monotonic()

    def tilt_feedback_callback(self, msg):
        self.tilt_us = int(msg.data)
        self.tilt_feedback_at = time.monotonic()

    @staticmethod
    def asks_weather(text):
        lower = text.lower()
        if any(term in lower for term in ("start tracking", "track person", "follow camera", "tracking on")):
            self.tracker_pub.publish(Bool(data=True))
            return "Camera person tracking enabled. Rover wheels remain stopped."
        if any(term in lower for term in ("stop tracking", "tracking off")):
            self.tracker_pub.publish(Bool(data=False))
            return "Camera person tracking stopped."
        return any(word in lower for word in (
            "weather", "temperature outside", "rain", "forecast",
            "मौसम", "बारिश", "बाहर का तापमान",
        ))

    @staticmethod
    def asks_time(text):
        lower = text.lower()
        return any(word in lower for word in (
            "what time", "tell time", "current time", "time now",
            "kitne baje", "कितने बजे", "समय",
        ))

    @staticmethod
    def local_time_reply():
        now = time.localtime()
        return time.strftime("The time is %I:%M %p.", now)

    def weather_reply(self):
        current = self.online_weather()
        temp = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        source = current.get("source", "current location")
        if temp is None:
            return "I could not get the current weather data."
        reply = f"Current weather at {source}: {temp:.0f} degrees Celsius"
        if humidity is not None:
            reply += f", humidity {humidity:.0f} percent"
        if wind is not None:
            reply += f", wind {wind:.0f} kilometres per hour"
        return reply + "."

    @staticmethod
    def asks_atlas_status(text):
        lower = text.lower()
        return any(word in lower for word in (
            "atlas status", "rover status", "battery", "sensor", "gps",
            "5g", "temperature", "fault", "problem", "recovery", "diagnostic",
            "एटलस", "रोवर", "बैटरी", "सेंसर",
            "जीपीएस", "तापमान",
        ))

    @staticmethod
    def asks_vision(text):
        lower = text.lower()
        exact_match = any(term in lower for term in (
            "what can you see", "what do you see", "can you see me",
            "describe what you see", "look at me", "camera see",
            "what you can see", "what are you seeing", "what is in front",
            "identify this", "recognize this", "recognise this",
            "kya dekh", "kya dikh", "dekh sakte", "dikh raha",
        ))
        # Hindi STT frequently changes word order or drops the subject. Match
        # the stable visual verbs instead of requiring one exact sentence.
        hindi_visual = any(term in lower for term in (
            "\u0926\u0947\u0916",  # dekh / see
            "\u0926\u093f\u0916",  # dikh / visible
            "\u0928\u091c\u0930",  # nazar / visible
        )) and any(term in lower for term in (
            "\u0915\u094d\u092f\u093e", "\u0915\u0941\u091b", "\u092e\u0941\u091d", "\u0915\u0948\u092e\u0930",
        ))
        english_visual = (
            ("see" in lower or "seeing" in lower or "look" in lower)
            and ("what" in lower or "can you" in lower or "camera" in lower)
        )
        return exact_match or hindi_visual or english_visual

    def vision_reply(self, text):
        hindi = any("\u0900" <= char <= "\u097f" for char in text)
        try:
            objects = json.loads(
                self.rover.get("camera_detections", "{}") or "{}"
            ).get("detections", [])
        except Exception:
            objects = []
        try:
            faces = json.loads(
                self.rover.get("camera_faces", "{}") or "{}"
            ).get("faces", [])
        except Exception:
            faces = []
        labels = []
        for item in objects:
            label = str(item.get("label", "object"))
            confidence = float(item.get("confidence", 0) or 0)
            if confidence >= 0.35 and label not in labels:
                labels.append(label)
        if faces:
            if hindi:
                extra = " और " + ", ".join(labels[:4]) if labels else ""
                return f"मैं कैमरे में {len(faces)} चेहरा देख रहा हूँ{extra}।"
            extra = " and " + ", ".join(labels[:4]) if labels else ""
            suffix = "s" if len(faces) != 1 else ""
            return f"I can currently see {len(faces)} face{suffix}{extra}."
        if labels:
            joined = ", ".join(labels[:5])
            return (f"कैमरे में अभी {joined} दिखाई दे रहा है।" if hindi else
                    f"I can currently see {joined} through the camera.")
        return ("कैमरा चालू है, लेकिन अभी कोई चेहरा या पहचानी गई वस्तु नहीं दिख रही।"
                if hindi else
                "The camera is live, but I do not currently detect a face or a recognized object.")

    def online_weather(self):
        lat = self.rover.get("latitude")
        lon = self.rover.get("longitude")
        location_source = "rover GPS"
        if lat is None or lon is None:
            # Project ATLAS home fallback; clearly labelled for the model.
            lat, lon = 28.6139, 77.2090
            location_source = "New Delhi fallback because rover GPS has no fix"
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "precipitation,rain,weather_code,wind_speed_10m"
                ),
                "timezone": "auto",
            },
            timeout=15,
        )
        response.raise_for_status()
        current = response.json().get("current", {})
        return {"source": location_source, "latitude": lat, "longitude": lon, **current}

    def transcribe(self, pcm):
        files = {"file": ("atlas.wav", self.wav_bytes(pcm), "audio/wav")}
        prompt = "Project ATLAS rover. Speech may be English, Hindi, or Hinglish."
        if self.pending_agent_action and time.monotonic() <= self.pending_agent_deadline:
            prompt += (
                " A movement confirmation is pending. The speaker will likely say "
                "confirm, yes confirm, okay proceed, haan, haan confirm, theek hai, "
                "or cancel. Transcribe those confirmation words accurately."
            )
        data = {
            "model": os.getenv("ATLAS_STT_MODEL", "gpt-4o-mini-transcribe"),
            "prompt": prompt,
        }
        response = requests.post(
            f"{API_BASE}/audio/transcriptions", headers=self.api_headers(),
            files=files, data=data, timeout=45,
        )
        response.raise_for_status()
        text = response.json().get("text", "").strip()
        # A silent clip can occasionally echo the prompt as a hypothesis.
        if text.lower().startswith("project atlas rover. speech may be"):
            return ""
        return text

    def answer(self, text):
        system = (
            "You are ATLAS, a friendly concise bilingual rover companion. "
            "Reply in the same language as the user: Hindi for Hindi, English "
            "for English, natural Hinglish for mixed speech. Limit replies to "
            "two short sentences. Never claim a physical action occurred. "
            "You have live camera perception through ATLAS ROS topics. Never "
            "say that you cannot see; describe only supplied camera perception "
            "or say that no recognized object is currently detected. "
            "Driving, navigation, follow-me, shell, package installation, and "
            "hardware changes require explicit confirmation. Autonomous motion "
            "requires a separate confirmation handled by the ATLAS safety bridge."
        )
        live_context = {}
        if self.asks_atlas_status(text):
            live_context["atlas_ros"] = dict(self.rover)
        if self.asks_vision(text):
            live_context["camera_perception"] = {
                "detections": self.rover.get("camera_detections", "{}"),
                "faces": self.rover.get("camera_faces", "{}"),
                "tracking": self.rover.get("camera_tracking_status", "unknown"),
            }
        if self.asks_weather(text):
            try:
                live_context["online_weather"] = self.online_weather()
            except Exception as exc:
                live_context["online_weather_error"] = str(exc)
        user_content = text
        if live_context:
            user_content += (
                "\n\nLIVE TOOL DATA (use only these current values; say when a "
                "value is unavailable):\n" + json.dumps(live_context, ensure_ascii=False)
            )
        messages = [{"role": "system", "content": system}]
        messages.extend(self.conversation[-6:])
        messages.append({"role": "user", "content": user_content})
        body = {
            "model": os.getenv("ATLAS_CHAT_MODEL", "gpt-4o-mini"),
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 160,
        }
        response = requests.post(
            f"{API_BASE}/chat/completions",
            headers={**self.api_headers(), "Content-Type": "application/json"},
            json=body, timeout=45,
        )
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"].strip()
        self.conversation.extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": reply},
        ])
        self.conversation = self.conversation[-6:]
        return reply

    def speech(self, text):
        model = os.getenv("ATLAS_TTS_MODEL", "tts-1")
        voice = os.getenv("ATLAS_TTS_VOICE", "alloy")
        cache_dir = os.path.expanduser("~/project_atlas/cache/voice")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.sha256(
            f"{model}\0{voice}\0{text}".encode("utf-8")
        ).hexdigest()
        cache_path = os.path.join(cache_dir, cache_key + ".pcm16k")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as cached:
                return cached.read()
        body = {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": "pcm",
        }
        if model == "gpt-4o-mini-tts":
            body["instructions"] = (
                "Speak warmly and clearly. Preserve the response language, "
                "including natural Hindi pronunciation and Hinglish."
            )
        response = requests.post(
            f"{API_BASE}/audio/speech",
            headers={**self.api_headers(), "Content-Type": "application/json"},
            json=body, timeout=60,
        )
        response.raise_for_status()
        # OpenAI PCM is 24 kHz, mono, signed 16-bit little-endian.
        pcm16, _ = audioop.ratecv(response.content, 2, 1, 24000, SAMPLE_RATE, None)
        with open(cache_path, "wb") as cached:
            cached.write(pcm16)
        return pcm16

    def local_speech(self, text):
        """Generate low-latency bilingual speech locally with Piper."""
        piper_root = os.path.expanduser("~/project_atlas/vendor/piper")
        binary = os.path.join(piper_root, "piper", "piper")
        is_hindi = any("\u0900" <= char <= "\u097f" for char in text)
        voice_name = (
            "hi_IN-pratham-medium" if is_hindi else "en_US-lessac-medium"
        )
        model = os.path.join(piper_root, "voices", voice_name + ".onnx")
        config = model + ".json"
        cache_dir = os.path.expanduser("~/project_atlas/cache/voice-local")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.sha256(
            f"{voice_name}\0{text}".encode("utf-8")
        ).hexdigest()
        cache_path = os.path.join(cache_dir, cache_key + ".pcm16k")
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as cached:
                return cached.read()
        try:
            with open(config, "r", encoding="utf-8") as source:
                source_rate = int(json.load(source)["audio"]["sample_rate"])
            result = subprocess.run(
                [binary, "--model", model, "--output_raw"],
                input=(text + "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=True,
                cwd=os.path.join(piper_root, "piper"),
            )
            pcm16, _ = audioop.ratecv(
                result.stdout, 2, 1, source_rate, SAMPLE_RATE, None
            )
            with open(cache_path, "wb") as cached:
                cached.write(pcm16)
            language = "HINDI" if is_hindi else "ENGLISH"
            self.publish("cloud", f"HYBRID: LOCAL {language} SPEECH")
            return pcm16
        except Exception as exc:
            self.publish("cloud", f"LOCAL TTS FALLBACK: {exc}")
            return self.speech(text)

    def speak_stream(self, text):
        """Stream TTS to the ESP32 instead of waiting for the full recording."""
        model = os.getenv("ATLAS_TTS_MODEL", "tts-1")
        body = {
            "model": model,
            "voice": os.getenv("ATLAS_TTS_VOICE", "alloy"),
            "input": text,
            "response_format": "pcm",
        }
        if model == "gpt-4o-mini-tts":
            body["instructions"] = (
                "Speak warmly and clearly in the response language, including Hindi."
            )
        response = requests.post(
            f"{API_BASE}/audio/speech",
            headers={**self.api_headers(), "Content-Type": "application/json"},
            json=body, timeout=75, stream=True,
        )
        response.raise_for_status()
        self.set_state("SPEAKING")
        self.ignore_mic_until = time.monotonic() + 300.0
        rate_state = None
        raw_carry = b""
        pending = bytearray()
        for raw in response.iter_content(chunk_size=4096):
            if not raw:
                continue
            raw = raw_carry + raw
            even_length = len(raw) & ~1
            raw_carry = raw[even_length:]
            raw = raw[:even_length]
            if not raw:
                continue
            converted, rate_state = audioop.ratecv(
                raw, 2, 1, 24000, SAMPLE_RATE, rate_state
            )
            pending.extend(converted)
            while len(pending) >= PLAY_CHUNK_BYTES:
                self.send_packet(PLAY_PCM, bytes(pending[:PLAY_CHUNK_BYTES]))
                del pending[:PLAY_CHUNK_BYTES]
        if pending:
            self.send_packet(PLAY_PCM, bytes(pending))
        time.sleep(0.3)
        while True:
            try:
                self.audio_q.get_nowait()
            except queue.Empty:
                break
        self.ignore_mic_until = time.monotonic() + 1.0

    def play(self, pcm):
        playback_seconds = len(pcm) / 2 / SAMPLE_RATE
        self.ignore_mic_until = time.monotonic() + playback_seconds + 1.0
        self.publish("state", "BUFFERING")
        self.publish("rgb", "WHITE")
        self.send_packet(STATE, b"STATE BUFFERING")
        if not self.send_packet(PLAY_BEGIN, struct.pack("<I", len(pcm))):
            raise RuntimeError("ESP32 playback buffer start failed")
        # Use the largest packet accepted by the ESP32 and pace it at the
        # actual 16 kHz playback duration. Sending faster causes buffer
        # overlap/clicking; tiny packets create excessive boundaries.
        chunk = PLAY_CHUNK_BYTES
        for pos in range(0, len(pcm), chunk):
            block = pcm[pos:pos + chunk]
            if not self.send_packet(PLAY_PCM, block):
                raise RuntimeError("ESP32 audio transport failed")
        self.set_state("SPEAKING")
        started = time.monotonic()
        if not self.send_packet(PLAY_END):
            raise RuntimeError("ESP32 playback commit failed")
        remaining = playback_seconds - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
        time.sleep(0.15)
        # Remove audio captured from ATLAS's own nearby speaker.
        while True:
            try:
                self.audio_q.get_nowait()
            except queue.Empty:
                break

    @staticmethod
    def is_motion_request(text):
        lower = text.lower()
        words = (
            "move", "drive", "forward", "backward", "turn", "follow me",
            "navigate", "चलो", "आगे", "पीछे", "मुड़", "फॉलो",
        )
        return any(word in lower for word in words)

    @staticmethod
    def remove_wake_phrase(text):
        cleaned = text
        found = False
        for phrase in (
            "hey atlas", "hi atlas", "hello atlas",
            "हे एटलस", "हाय एटलस", "हेलो एटलस",
        ):
            if phrase in cleaned.lower():
                cleaned = re.sub(
                    re.escape(phrase), "", cleaned, flags=re.IGNORECASE
                )
                found = True
        return found, cleaned.strip(" \t\r\n,.:;!?।")

    def command_servo(self, axis, target, timeout=1.5):
        # Arducam B0283 180-degree servos: reserve mechanical end-stop margin.
        target = max(500, min(2500, int(target)))
        started = time.monotonic()
        publisher = self.pan_pub if axis == "pan" else self.tilt_pub
        publisher.publish(Int32(data=target))
        while time.monotonic() - started < timeout:
            actual = self.pan_us if axis == "pan" else self.tilt_us
            feedback_at = (
                self.pan_feedback_at if axis == "pan" else self.tilt_feedback_at
            )
            if feedback_at >= started and abs(actual - target) <= 10:
                return True
            time.sleep(0.05)
        return False

    def handle_safe_hardware_request(self, text):
        """Execute only bounded camera/AI actions; never wheel motion."""
        lower = text.lower()
        # Match Hindi inflections such as कैमरा, कैमरे and कैमरे को.
        direction_words = (
            "up", "down", "ऊपर", "नीचे", "اوپر", "نیچے",
        )
        camera_named = (
            "camera" in lower or "कैमर" in lower or "کیمر" in lower
            or any(word in lower for word in direction_words)
        )
        hindi_request = any("\u0900" <= char <= "\u097f" for char in text)
        if camera_named:
            if any(word in lower for word in ("center", "centre", "मध्य", "सीधा")):
                ok = self.command_servo("pan", 1300)
                ok = self.command_servo("tilt", 2100) and ok
                if ok:
                    return "कैमरा बीच में कर दिया।" if hindi_request else "Camera centered."
                return "कैमरा प्रतिक्रिया नहीं दे रहा।" if hindi_request else "Camera did not confirm movement."
            if any(word in lower for word in ("left", "बाएं", "बायें")):
                if self.command_servo("pan", self.pan_us - 160):
                    return "कैमरा बाईं ओर कर दिया।" if hindi_request else "Camera moved left."
                return "कैमरा प्रतिक्रिया नहीं दे रहा।" if hindi_request else "Camera did not confirm movement."
            if any(word in lower for word in ("right", "दाएं", "दायें")):
                if self.command_servo("pan", self.pan_us + 160):
                    return "कैमरा दाईं ओर कर दिया।" if hindi_request else "Camera moved right."
                return "कैमरा प्रतिक्रिया नहीं दे रहा।" if hindi_request else "Camera did not confirm movement."
            if any(word in lower for word in ("up", "ऊपर", "اوپر")):
                if self.tilt_us >= 2500:
                    return "कैमरा पहले से सबसे ऊपर है।" if hindi_request else "Camera is already at its upper limit."
                if self.command_servo("tilt", self.tilt_us + 180):
                    return "कैमरा ऊपर कर दिया।" if hindi_request else "Camera moved up."
                return "कैमरा प्रतिक्रिया नहीं दे रहा।" if hindi_request else "Camera did not confirm movement."
            if any(word in lower for word in ("down", "नीचे", "نیچے")):
                if self.tilt_us <= 700:
                    return "कैमरा पहले से सबसे नीचे है।" if hindi_request else "Camera is already at its lower limit."
                if self.command_servo("tilt", self.tilt_us - 180):
                    return "कैमरा नीचे कर दिया।" if hindi_request else "Camera moved down."
                return "कैमरा प्रतिक्रिया नहीं दे रहा।" if hindi_request else "Camera did not confirm movement."
        ai_named = any(term in lower for term in (
            "object detection", "ai camera", "ऑब्जेक्ट डिटेक्शन", "एआई कैमरा",
        ))
        if ai_named and any(term in lower for term in (" on", "enable", "चालू")):
            self.ai_pub.publish(Bool(data=True))
            return "AI object detection enabled."
        if ai_named and any(term in lower for term in (" off", "disable", "बंद")):
            self.ai_pub.publish(Bool(data=False))
            return "AI object detection disabled."
        return None

    def execute_agent_action(self, action):
        """Publish only allowlisted high-level requests; never raw motor commands."""
        if action.startswith("voice_"):
            return self.execute_voice_motion(action)
        if action == "follow_person":
            self.ai_pub.publish(Bool(data=True))
            self.tracker_pub.publish(Bool(data=True))
            self.follow_pub.publish(Bool(data=True))
            self.publish("action", "AGENT TOOL: follow_person")
            return "Follow mode started at low speed. Say stop following at any time."
        if action == "stop_following":
            self.follow_pub.publish(Bool(data=False))
            self.publish_voice_stop()
            self.publish("action", "AGENT TOOL: stop_following")
            return "Follow mode stopped."
        publisher = self.agent_pubs.get(action)
        if publisher is None:
            return "That ATLAS action is not allowed."
        publisher.publish(Empty())
        labels = {
            "start_exploration": "Autonomous mapping requested.",
            "stop_exploration": "Autonomous motion and mapping goals stopped.",
            "set_home": "Current location requested as home.",
            "return_home": "Safe return-home navigation requested.",
        }
        message = labels[action]
        self.publish("action", f"AGENT TOOL: {action}")
        return message

    def publish_voice_stop(self):
        zero = Twist()
        for _ in range(6):
            self.voice_drive_pub.publish(zero)
            time.sleep(0.04)

    def execute_voice_motion(self, action):
        """Execute one low-speed, time-limited motion through the safety mux."""
        commands = {
            "voice_forward": (0.18, 0.0, 0.70, "Moving forward briefly."),
            "voice_backward": (-0.12, 0.0, 0.60, "Moving backward briefly."),
            "voice_left": (0.0, 0.55, 0.55, "Turning left briefly."),
            "voice_right": (0.0, -0.55, 0.55, "Turning right briefly."),
        }
        if action not in commands:
            return "That voice movement is not allowed."
        linear, angular, duration, reply = commands[action]
        front = float(self.rover.get("ultrasonic_front_mm", -1) or -1)
        if linear > 0 and 0 < front < 280:
            self.publish("action", f"BLOCKED: front obstacle {front:.0f} mm")
            return f"Movement blocked. The front obstacle is {front:.0f} millimetres away."
        command = Twist()
        command.linear.x = linear
        command.angular.z = angular
        deadline = time.monotonic() + duration
        self.publish("action", f"EXECUTING: {action} for {duration:.2f}s")
        try:
            while time.monotonic() < deadline:
                self.voice_drive_pub.publish(command)
                time.sleep(0.08)
        finally:
            self.publish_voice_stop()
        return reply

    def handle_agent_request(self, text):
        """Two-step voice gate for motion-capable autonomy tools."""
        lower = text.lower().strip()
        now = time.monotonic()
        confirm_words = (
            "confirm", "yes confirm", "yes", "proceed", "go ahead",
            "haan confirm", "ha confirm", "haan", "हाँ", "हां", "पुष्टि", "हाँ पुष्टि",
            "okay confirm", "ok confirm", "okay proceed", "ok proceed",
            "theek hai", "thik hai", "ठीक है", "जी हाँ", "जी हां",
            "ہاں", "ہاں، میں تیار ہوں", "ہاں میں تیار ہوں", "جی ہاں",
            "main taiyar hoon", "mein taiyar hun", "i am ready", "i'm ready",
            # Observed STT substitution for Dhruv saying "confirm".
            "干放",
        )
        cancel_words = (
            "cancel", "do not", "don't", "no cancel", "no", "stop",
            "रद्द", "नहीं", "मत चलो", "मत करो",
        )

        if self.pending_agent_action and now > self.pending_agent_deadline:
            self.pending_agent_action = None
            self.publish("confirmation", "EXPIRED")

        if self.pending_agent_action and any(word in lower for word in cancel_words):
            self.pending_agent_action = None
            self.pending_agent_deadline = 0.0
            self.publish("confirmation", "CANCELLED")
            return "The pending autonomous action was cancelled."

        if self.pending_agent_action and any(word in lower for word in confirm_words):
            action = self.pending_agent_action
            self.pending_agent_action = None
            self.pending_agent_deadline = 0.0
            self.publish("confirmation", f"CONFIRMED: {action}")
            return self.execute_agent_action(action)

        if lower == "stop" or any(phrase in lower for phrase in (
            "emergency stop", "stop rover", "stop now", "halt",
            "stop mapping", "stop exploration",
            "stop autonomous", "stop autonomy", "मैपिंग बंद", "रुको",
            "stop following", "stop follow", "do not follow", "फॉलो बंद", "पीछा बंद",
        )):
            self.pending_agent_action = None
            self.pending_agent_deadline = 0.0
            self.follow_pub.publish(Bool(data=False))
            self.publish_voice_stop()
            self.execute_agent_action("stop_exploration")
            return "ATLAS motion and follow mode stopped."

        if any(phrase in lower for phrase in (
            "set home", "save home", "this is home", "घर सेट", "होम सेट",
        )):
            return self.execute_agent_action("set_home")

        requested = None
        if any(phrase in lower for phrase in (
            "start mapping", "start exploration", "map this room",
            "auto mapping", "मैपिंग शुरू", "कमरा मैप",
        )):
            requested = "start_exploration"
        elif any(phrase in lower for phrase in (
            "return home", "go home", "come back home", "घर वापस",
        )):
            requested = "return_home"
        elif any(phrase in lower for phrase in (
            "move forward", "drive forward", "go forward", "forward",
            "आगे चलो", "आगे बढ़ो", "मूव फॉरवर्ड", "फॉरवर्ड चलो",
            "آگے بڑھو", "آگے چلو", "موو فارورڈ",
        )):
            requested = "voice_forward"
        elif any(phrase in lower for phrase in (
            "move backward", "drive backward", "go backward", "reverse", "backward",
            "पीछे चलो", "पीछे जाओ", "मूव बैकवर्ड", "پیچھے چلو", "موو بیک ورڈ",
        )):
            requested = "voice_backward"
        elif any(phrase in lower for phrase in (
            "turn left", "rotate left", "बाएं मुड़ो", "बायें मुड़ो",
            "टर्न लेफ्ट", "بائیں مڑو", "ٹرن لیفٹ",
        )):
            requested = "voice_left"
        elif any(phrase in lower for phrase in (
            "turn right", "rotate right", "दाएं मुड़ो", "दायें मुड़ो",
            "टर्न राइट", "دائیں مڑو", "ٹرن رائٹ",
        )):
            requested = "voice_right"
        elif any(phrase in lower for phrase in (
            "follow me", "start following", "come with me", "फॉलो मी",
            "मेरा पीछा करो", "मेरे पीछे आओ", "میرے پیچھے آؤ", "فالو می",
        )):
            requested = "follow_person"

        if requested:
            self.pending_agent_action = requested
            self.pending_agent_deadline = now + 45.0
            self.publish("confirmation", f"WAITING: {requested}")
            return (
                "Safety confirmation required. Say confirm within forty-five seconds, "
                "or say cancel."
            )
        return None

    def process_utterance(self, pcm):
        try:
            self.set_state("THINKING")
            self.publish("cloud", "TRANSCRIBING")
            text = self.transcribe(pcm)
            if not text:
                self.set_state("IDLE")
                return
            self.publish("transcript", text)
            wake_found, command_text = self.remove_wake_phrase(text)
            if wake_found and not command_text:
                self.awake_until = time.monotonic() + 8.0
                self.publish("intent", "WAKE WORD")
                self.publish("response", "Listening for command")
                self.set_state("IDLE")
                return
            if not wake_found and time.monotonic() > self.awake_until:
                normalized = text.lower().strip(" \t\r\n,.:;!?।")
                false_silence = {
                    "here it is", "there it is", "thank you",
                    "thanks for watching", "you", "bye",
                }
                if normalized in false_silence:
                    self.publish("intent", "IGNORED - SILENCE/NOISE")
                    self.set_state("IDLE")
                    return
            if command_text:
                text = command_text
            self.awake_until = 0.0
            agent_reply = self.handle_agent_request(text)
            safe_reply = None if agent_reply else self.handle_safe_hardware_request(text)
            if agent_reply:
                self.publish("intent", "ATLAS AGENT TOOL REQUEST")
                reply = agent_reply
            elif safe_reply:
                self.publish("intent", "SAFE HARDWARE CONTROL")
                self.publish("action", safe_reply)
                reply = safe_reply
            elif self.is_motion_request(text):
                self.publish("intent", "MOTION REQUEST")
                self.publish("action", "BLOCKED - CONFIRMATION REQUIRED")
                reply = (
                    "Movement request received. Please confirm it using the safe control."
                    if not any("\u0900" <= c <= "\u097f" for c in text)
                    else "चलने का निर्देश मिला। कृपया सुरक्षित कंट्रोल से पुष्टि करें।"
                )
            elif self.asks_vision(text):
                self.publish("intent", "LIVE CAMERA PERCEPTION")
                reply = self.vision_reply(text)
            elif self.asks_time(text):
                self.publish("intent", "TIME")
                reply = self.local_time_reply()
            elif self.asks_weather(text):
                self.publish("intent", "LIVE WEATHER")
                try:
                    reply = self.weather_reply()
                except Exception as exc:
                    self.publish("cloud", f"WEATHER ERROR: {exc}")
                    reply = "I cannot reach the live weather service right now."
            else:
                self.publish("intent", "CONVERSATION")
                self.publish("cloud", "OPENAI ONLINE")
                reply = self.answer(text)
            self.publish("response", reply)
            # The speech API can generate slower than real time on the rover's
            # connection. Buffering fully prevents audible gaps and stutter.
            self.play(self.local_speech(reply))
            self.publish("action", "NONE")
            self.set_state("IDLE")
        except Exception as exc:
            self.publish("cloud", f"API ERROR: {exc}")
            self.ignore_mic_until = time.monotonic() + 1.0
            self.set_state("ERROR")
            time.sleep(1)
            self.set_state("IDLE")

    def voice_loop(self):
        pre_roll = []
        recording = []
        speaking_frames = 0
        silent_frames = 0
        active = False
        while self.running:
            try:
                frame = self.audio_q.get(timeout=1)
            except queue.Empty:
                continue
            if len(frame) < 2:
                continue
            if time.monotonic() < self.ignore_mic_until:
                continue
            rms = audioop.rms(frame, 2)
            if time.monotonic() < self.calibrate_until:
                self.noise_floor = 0.85 * self.noise_floor + 0.15 * rms
                continue
            # The board's dual microphones have conservative gain. Keep the
            # adaptive gate above room noise while accepting a nearby voice.
            # Never let a noisy startup calibration make ATLAS effectively
            # deaf. The cap preserves sensitivity to a nearby speaking voice.
            threshold = min(450.0, max(330.0, self.noise_floor * 1.8))
            voiced = rms > threshold
            if not active and not voiced:
                self.noise_floor = 0.98 * self.noise_floor + 0.02 * rms
            pre_roll.append(frame)
            pre_roll = pre_roll[-10:]
            if not active and voiced:
                active = True
                recording = list(pre_roll)
                speaking_frames = 1
                silent_frames = 0
                self.set_state("LISTENING")
                continue
            if active:
                recording.append(frame)
                if voiced:
                    speaking_frames += 1
                    silent_frames = 0
                else:
                    silent_frames += 1
                # 30 silent frames ~= 1.2 s; permits a natural pause after
                # the wake phrase without splitting off the real question.
                if silent_frames >= 30 or len(recording) >= 300:
                    active = False
                    # Four 40 ms voiced frames is enough for a short wake
                    # phrase such as "Hey Atlas".
                    if speaking_frames >= 4:
                        if self.speech_lock.acquire(blocking=False):
                            try:
                                self.process_utterance(b"".join(recording))
                            finally:
                                self.speech_lock.release()
                        else:
                            self.set_state("IDLE")
                    else:
                        self.set_state("IDLE")
                    recording = []

    def destroy_node(self):
        self.running = False
        try:
            if self.serial:
                self.serial.close()
        finally:
            super().destroy_node()


def main():
    rclpy.init()
    node = AtlasVoice()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
