# Temporary standalone diagnostic — NOT hub firmware

This manually commissioned sketch was used only to compare A4/A5 digital reads
in GPIO pull-up, idle Wire and GPIO-after-Wire modes. It does not operate motors,
servos or peripheral UARTs. It replaces normal hub telemetry while installed.

Do not upload automatically. Requires explicit operator approval, disconnected
A4/A5 and parallel SDA/SCL connections, motor/servo power OFF, exact UNO identity,
verified saved hub restore image and operator access to RESET. Native USB entry
and restoration may require manual double RESET and a full power cycle.

LOW readings alone are not proof of damaged hardware; an independent reference
or voltage measurement is needed. See
[observations and restoration](../../docs/audits/ATLAS_I2C_USB_RECOVERY_2026-10-20.md).
