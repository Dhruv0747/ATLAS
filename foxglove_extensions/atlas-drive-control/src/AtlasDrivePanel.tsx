import { MessageEvent, PanelExtensionContext } from "@foxglove/extension";
import {
  PointerEvent as ReactPointerEvent,
  ReactElement,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";

type Twist = {
  linear: { x: number; y: number; z: number };
  angular: { x: number; y: number; z: number };
};

type StringMessage = { data?: string };
type Int32Message = { data?: number };
type Float32Message = { data?: number };
type UltrasonicReadings = {
  front?: number;
  left?: number;
  right?: number;
  rear?: number;
};
type AutonomyState = {
  phase?: string;
  severity?: string;
  summary?: string;
  decision?: string;
  goal?: string;
  behavior?: string;
  clearance_m?: { front?: number; left?: number; right?: number; rear?: number };
  map?: { known_percent?: number; plan_points?: number };
  sensors?: {
    lidar?: string;
    odometry?: string;
    slam_map?: string;
    ai_camera?: string;
  };
};
const CMD_TOPIC = "/cmd_vel_teleop";
const MISSION_TOPICS = [
  "/atlas/start_exploration",
  "/atlas/stop_exploration",
  "/atlas/set_home",
  "/atlas/return_home",
] as const;
const CAMERA_TOPICS = [
  "/atlas/camera/pan_left",
  "/atlas/camera/pan_right",
  "/atlas/camera/tilt_up",
  "/atlas/camera/tilt_down",
  "/atlas/camera/home",
] as const;
const MAX_LINEAR = 0.2;
const MAX_ANGULAR = 0.45;
const PUBLISH_HZ = 20;

function ultrasonicColor(value: number | undefined): string {
  if (value == undefined || value < 0) {
    return "#8099b5";
  }
  if (value < 250) {
    return "#ff4d5a";
  }
  if (value < 450) {
    return "#ffc857";
  }
  return "#41d18b";
}

function ultrasonicLabel(value: number | undefined): string {
  if (value == undefined) {
    return "WAITING";
  }
  if (value < 0) {
    return "NO ECHO";
  }
  return `${(value / 1000).toFixed(2)} m`;
}

function zeroTwist(): Twist {
  return {
    linear: { x: 0, y: 0, z: 0 },
    angular: { x: 0, y: 0, z: 0 },
  };
}

function AtlasDrivePanel({ context }: { context: PanelExtensionContext }): ReactElement {
  const padRef = useRef<HTMLDivElement>(null);
  const activePointer = useRef<number>();
  const commandRef = useRef<Twist>(zeroTwist());
  const [throttle, setThrottle] = useState(0);
  const [steering, setSteering] = useState(0);
  const [driveMode, setDriveMode] = useState("STOPPED");
  const [safety, setSafety] = useState("Waiting for safety status");
  const [missionStatus, setMissionStatus] = useState("READY");
  const [odometrySource, setOdometrySource] = useState("unknown");
  const [autonomy, setAutonomy] = useState<AutonomyState>();
  const [cameraPanUs, setCameraPanUs] = useState(1300);
  const [cameraTiltUs, setCameraTiltUs] = useState(2100);
  const [ultrasonic, setUltrasonic] = useState<UltrasonicReadings>({});
  const [ultrasonicStatus, setUltrasonicStatus] = useState("Waiting for sensor hub");
  const [canPublish, setCanPublish] = useState(false);
  const [renderDone, setRenderDone] = useState<(() => void)>();

  const publish = useCallback(
    (message: Twist) => {
      context.publish?.(CMD_TOPIC, message);
    },
    [context],
  );

  const setCommand = useCallback((linear: number, angular: number) => {
    const message: Twist = {
      linear: { x: linear, y: 0, z: 0 },
      angular: { x: 0, y: 0, z: angular },
    };
    commandRef.current = message;
    setThrottle(linear);
    setSteering(angular);
  }, []);

  const stop = useCallback(() => {
    activePointer.current = undefined;
    setCommand(0, 0);
    publish(zeroTwist());
  }, [publish, setCommand]);

  const publishMission = useCallback(
    (topic: (typeof MISSION_TOPICS)[number]) => {
      context.publish?.(topic, {});
    },
    [context],
  );

  const publishCamera = useCallback(
    (topic: (typeof CAMERA_TOPICS)[number]) => {
      context.publish?.(topic, {});
    },
    [context],
  );

  const updateFromPointer = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const bounds = padRef.current?.getBoundingClientRect();
      if (!bounds) {
        return;
      }
      const normalizedX = Math.max(
        -1,
        Math.min(1, (event.clientX - (bounds.left + bounds.width / 2)) / (bounds.width / 2)),
      );
      const normalizedY = Math.max(
        -1,
        Math.min(1, ((bounds.top + bounds.height / 2) - event.clientY) / (bounds.height / 2)),
      );
      const deadband = 0.08;
      const x = Math.abs(normalizedX) < deadband ? 0 : normalizedX;
      const y = Math.abs(normalizedY) < deadband ? 0 : normalizedY;
      // Quadratic steering provides precise control near centre.
      const shapedSteering = Math.sign(x) * x * x * MAX_ANGULAR;
      setCommand(y * MAX_LINEAR, shapedSteering);
    },
    [setCommand],
  );

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      activePointer.current = event.pointerId;
      event.currentTarget.setPointerCapture(event.pointerId);
      updateFromPointer(event);
    },
    [updateFromPointer],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (activePointer.current === event.pointerId) {
        updateFromPointer(event);
      }
    },
    [updateFromPointer],
  );

  useLayoutEffect(() => {
    context.onRender = (renderState, done) => {
      for (const event of renderState.currentFrame ?? []) {
        const message = (event as MessageEvent<StringMessage>).message;
        if (event.topic === "/atlas/drive_mode") {
          setDriveMode(message.data ?? "unknown");
        } else if (event.topic === "/atlas/safety_status") {
          setSafety(message.data ?? "unknown");
        } else if (event.topic === "/yahboom/odom_source") {
          setOdometrySource(message.data ?? "unknown");
        } else if (event.topic === "/atlas/mission_status") {
          setMissionStatus(message.data ?? "unknown");
        } else if (event.topic === "/atlas/autonomy_state" && message.data) {
          try {
            setAutonomy(JSON.parse(message.data) as AutonomyState);
          } catch {
            setAutonomy({
              phase: "STATUS_ERROR",
              summary: "Autonomy status JSON could not be decoded",
            });
          }
        } else if (event.topic === "/camera/bottom_servo_us") {
          setCameraPanUs((event as MessageEvent<Int32Message>).message.data ?? 1300);
        } else if (event.topic === "/camera/second_servo_us") {
          setCameraTiltUs((event as MessageEvent<Int32Message>).message.data ?? 2100);
        } else if (event.topic === "/ultrasonic/status") {
          setUltrasonicStatus(message.data ?? "unknown");
        } else if (event.topic.startsWith("/ultrasonic/") && event.topic.endsWith("_mm")) {
          const value = (event as MessageEvent<Float32Message>).message.data;
          if (value != undefined) {
            const direction = event.topic.slice("/ultrasonic/".length, -"_mm".length) as
              | "front"
              | "left"
              | "right"
              | "rear";
            setUltrasonic((previous) => ({ ...previous, [direction]: value }));
          }
        }
      }
      setRenderDone(() => done);
    };
    context.watch("currentFrame");
    context.subscribe([
      { topic: "/atlas/drive_mode" },
      { topic: "/atlas/safety_status" },
      { topic: "/yahboom/odom_source" },
      { topic: "/atlas/mission_status" },
      { topic: "/atlas/autonomy_state" },
      { topic: "/camera/bottom_servo_us" },
      { topic: "/camera/second_servo_us" },
      { topic: "/ultrasonic/front_mm" },
      { topic: "/ultrasonic/left_mm" },
      { topic: "/ultrasonic/right_mm" },
      { topic: "/ultrasonic/rear_mm" },
      { topic: "/ultrasonic/status" },
    ]);
    context.advertise?.(CMD_TOPIC, "geometry_msgs/msg/Twist");
    for (const topic of MISSION_TOPICS) {
      context.advertise?.(topic, "std_msgs/msg/Empty");
    }
    for (const topic of CAMERA_TOPICS) {
      context.advertise?.(topic, "std_msgs/msg/Empty");
    }
    setCanPublish(context.publish != undefined && context.advertise != undefined);

    return () => {
      publish(zeroTwist());
      context.unadvertise?.(CMD_TOPIC);
      for (const topic of MISSION_TOPICS) {
        context.unadvertise?.(topic);
      }
      for (const topic of CAMERA_TOPICS) {
        context.unadvertise?.(topic);
      }
    };
  }, [context, publish]);

  useEffect(() => {
    renderDone?.();
  }, [renderDone]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (activePointer.current != undefined) {
        publish(commandRef.current);
      }
    }, 1000 / PUBLISH_HZ);
    return () => {
      window.clearInterval(timer);
      publish(zeroTwist());
    };
  }, [publish]);

  const fault =
    odometrySource === "commanded_encoder_stale" ||
    safety.includes("ENCODERS NOT MOVING") ||
    safety.startsWith("STOP:") ||
    autonomy?.severity === "ERROR";

  const statusColor =
    fault || autonomy?.severity === "ERROR"
      ? "#ff4d5a"
      : safety.includes("CAUTION") || autonomy?.severity === "WARN"
        ? "#ffc857"
        : "#41d18b";
  const knobLeft = 50 + (steering / MAX_ANGULAR) * 42;
  const knobTop = 50 - (throttle / MAX_LINEAR) * 42;
  const rearClearance = autonomy?.clearance_m?.rear;
  const rearColor =
    rearClearance == undefined
      ? "#8099b5"
      : rearClearance < 0.25
        ? "#ff4d5a"
        : rearClearance < 0.45
          ? "#ffc857"
          : "#41d18b";

  return (
    <div
      style={{
        boxSizing: "border-box",
        height: "100%",
        padding: 14,
        color: "#ecf3ff",
        background: "linear-gradient(145deg, #07111f, #101d31)",
        fontFamily: "Inter, Segoe UI, sans-serif",
        overflow: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ color: "#62c8ff", fontSize: 12, fontWeight: 700 }}>PROJECT ATLAS</div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Smooth Drive</div>
        </div>
        <button
          onClick={stop}
          style={{
            border: 0,
            borderRadius: 8,
            padding: "8px 16px",
            color: "white",
            background: "#d9293e",
            fontWeight: 900,
            cursor: "pointer",
          }}
        >
          STOP
        </button>
      </div>

      <div
        style={{
          marginTop: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          border: `2px solid ${rearColor}`,
          borderRadius: 8,
          padding: "8px 10px",
          background: `${rearColor}18`,
        }}
      >
        <div>
          <div style={{ color: rearColor, fontSize: 10, fontWeight: 900 }}>REAR VIEW · LIDAR</div>
          <div style={{ color: "#9db0c8", fontSize: 10 }}>Reverse-direction clearance</div>
        </div>
        <div style={{ color: rearColor, fontSize: 19, fontWeight: 900 }}>
          {rearClearance?.toFixed(2) ?? "--"} m
        </div>
      </div>

      <div style={{ marginTop: 8 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 5 }}>
          {([ 
            ["/atlas/camera/pan_left", "CAM ←"],
            ["/atlas/camera/tilt_up", "CAM ↑"],
            ["/atlas/camera/home", "HOME"],
            ["/atlas/camera/tilt_down", "CAM ↓"],
            ["/atlas/camera/pan_right", "CAM →"],
          ] as const).map(([topic, label]) => (
            <button
              key={`fixed-${topic}-${label}`}
              onClick={() => {
                publishCamera(topic);
              }}
              style={{
                border: "1px solid #2f668d",
                borderRadius: 6,
                padding: "7px 2px",
                color: "white",
                background: label === "HOME" ? "#264560" : "#123454",
                fontSize: 9,
                fontWeight: 800,
                cursor: canPublish ? "pointer" : "not-allowed",
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 3, color: "#7f94ac", fontSize: 9, textAlign: "center" }}>
          Camera pan {cameraPanUs} us · tilt {cameraTiltUs} us
        </div>
      </div>

      <div
        style={{
          marginTop: 12,
          border: `1px solid ${statusColor}`,
          borderRadius: 8,
          padding: 10,
          background: `${statusColor}18`,
        }}
      >
        <div style={{ color: statusColor, fontWeight: 800 }}>
          {fault ? "DRIVE FAULT" : (autonomy?.phase ?? driveMode)}
        </div>
        <div style={{ marginTop: 4, fontSize: 12 }}>{autonomy?.summary ?? safety}</div>
        {autonomy?.decision && (
          <div style={{ marginTop: 4, color: "#c9d7e8", fontSize: 11 }}>
            Decision: {autonomy.decision}
          </div>
        )}
        <div style={{ marginTop: 3, color: "#9db0c8", fontSize: 11 }}>
          Odometry: {odometrySource}
        </div>
      </div>

      {autonomy && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 6,
            marginTop: 8,
          }}
        >
          {[
            ["FRONT", `${autonomy.clearance_m?.front?.toFixed(2) ?? "--"} m`],
            ["LEFT", `${autonomy.clearance_m?.left?.toFixed(2) ?? "--"} m`],
            ["RIGHT", `${autonomy.clearance_m?.right?.toFixed(2) ?? "--"} m`],
            ["REAR", `${autonomy.clearance_m?.rear?.toFixed(2) ?? "--"} m`],
            ["MAP", `${autonomy.map?.known_percent?.toFixed(1) ?? "--"}% known`],
            ["PATH", `${autonomy.map?.plan_points ?? 0} points`],
            ["AI FEED", autonomy.sensors?.ai_camera ?? "UNKNOWN"],
          ].map(([label, value]) => (
            <div
              key={label}
              style={{ padding: 7, borderRadius: 7, background: "#ffffff0b" }}
            >
              <div style={{ color: "#8099b5", fontSize: 9 }}>{label}</div>
              <div style={{ fontSize: 11, fontWeight: 800 }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      <div
        style={{
          marginTop: 10,
          border: "1px solid #294866",
          borderRadius: 8,
          padding: 9,
          background: "#071321a8",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <div style={{ color: "#62c8ff", fontSize: 11, fontWeight: 900 }}>
            LIVE ULTRASONIC
          </div>
          <div style={{ color: "#8099b5", fontSize: 9, textAlign: "right" }}>
            raw sensor range
          </div>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
            gap: 6,
            marginTop: 7,
          }}
        >
          {(["front", "left", "right", "rear"] as const).map((direction) => {
            const value = ultrasonic[direction];
            const color = ultrasonicColor(value);
            return (
              <div
                key={`ultrasonic-${direction}`}
                style={{
                  minWidth: 0,
                  padding: "7px 4px",
                  border: `1px solid ${color}`,
                  borderRadius: 7,
                  background: `${color}12`,
                  textAlign: "center",
                }}
              >
                <div style={{ color: "#9db0c8", fontSize: 8, fontWeight: 800 }}>
                  {direction.toUpperCase()}
                </div>
                <div style={{ color, fontSize: 12, fontWeight: 900, whiteSpace: "nowrap" }}>
                  {ultrasonicLabel(value)}
                </div>
                <div style={{ color: "#607891", fontSize: 8 }}>
                  {value != undefined && value >= 0 ? `${Math.round(value)} mm` : "—"}
                </div>
              </div>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 6,
            color: ultrasonicStatus.startsWith("ok") ? "#41d18b" : "#ffc857",
            fontSize: 9,
            overflowWrap: "anywhere",
          }}
        >
          HUB: {ultrasonicStatus}
        </div>
      </div>

      <div
        ref={padRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={stop}
        onPointerCancel={stop}
        onLostPointerCapture={stop}
        style={{
          position: "relative",
          width: "min(82%, 310px)",
          aspectRatio: "1",
          margin: "18px auto 10px",
          borderRadius: "50%",
          border: "2px solid #294866",
          background:
            "radial-gradient(circle at center, #152b42 0 12%, #0b1b2d 13% 64%, #071321 65%)",
          boxShadow: "inset 0 0 28px #0009, 0 0 22px #1f9cf033",
          touchAction: "none",
          cursor: canPublish ? "crosshair" : "not-allowed",
          userSelect: "none",
        }}
      >
        <div style={{ position: "absolute", top: 8, left: "46%", color: "#7f9ab7" }}>↑</div>
        <div style={{ position: "absolute", bottom: 8, left: "46%", color: "#7f9ab7" }}>↓</div>
        <div style={{ position: "absolute", left: 10, top: "46%", color: "#7f9ab7" }}>←</div>
        <div style={{ position: "absolute", right: 10, top: "46%", color: "#7f9ab7" }}>→</div>
        <div
          style={{
            position: "absolute",
            left: `${knobLeft}%`,
            top: `${knobTop}%`,
            width: 54,
            height: 54,
            transform: "translate(-50%, -50%)",
            borderRadius: "50%",
            background: "linear-gradient(145deg, #66d5ff, #147cc7)",
            border: "3px solid #bcecff",
            boxShadow: "0 5px 18px #000b",
            pointerEvents: "none",
          }}
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div style={{ padding: 8, borderRadius: 7, background: "#ffffff0b" }}>
          <div style={{ color: "#8099b5", fontSize: 11 }}>FORWARD</div>
          <b>{throttle.toFixed(2)} m/s</b>
        </div>
        <div style={{ padding: 8, borderRadius: 7, background: "#ffffff0b" }}>
          <div style={{ color: "#8099b5", fontSize: 11 }}>STEERING</div>
          <b>{steering.toFixed(2)} rad/s</b>
        </div>
      </div>
      <div style={{ marginTop: 9, color: "#7f94ac", fontSize: 11 }}>
        Drag diagonally to combine forward movement and steering. Releasing the control stops the rover.
      </div>

      <div
        style={{
          marginTop: 12,
          borderTop: "1px solid #294866",
          paddingTop: 10,
        }}
      >
        <div style={{ color: "#62c8ff", fontSize: 11, fontWeight: 800 }}>AUTONOMY</div>
        <div style={{ margin: "5px 0 8px", color: "#b7c8dc", fontSize: 11 }}>
          {missionStatus}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          {[
            ["/atlas/start_exploration", "START AUTO MAP", "#167c56"],
            ["/atlas/stop_exploration", "STOP + SAVE", "#b83d45"],
            ["/atlas/set_home", "SET HOME", "#2769a8"],
            ["/atlas/return_home", "RETURN HOME", "#7656b5"],
          ].map(([topic, label, color]) => (
            <button
              key={topic}
              onClick={() => {
                publishMission(topic as (typeof MISSION_TOPICS)[number]);
              }}
              style={{
                border: "1px solid #ffffff24",
                borderRadius: 7,
                padding: "8px 5px",
                color: "white",
                background: color,
                fontSize: 10,
                fontWeight: 800,
                cursor: canPublish ? "pointer" : "not-allowed",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function initAtlasDrivePanel(context: PanelExtensionContext): () => void {
  const root = createRoot(context.panelElement);
  root.render(<AtlasDrivePanel context={context} />);
  return () => {
    root.unmount();
  };
}
