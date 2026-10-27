# B4 binding observation and corrected input-path diagnosis

Owner reports receiver LED stops blinking when transmitter ON, resumes blinking when OFF. This supports a working radio link, but does not establish serial output format or valid channel reception. Owner subsequently confirms transmitter currently OFF. No power-on, COM access, wiring, reset, service change or flash operation in this investigation.

## Correction and compiled evidence

Prior report's PA2/PA3 discrepancy is withdrawn: enlarged saved manufacturer schematic shows RXD2 at MCU pin17 labelled PA3/U2_RX/ADC3. PA2/U2_TX/ADC2 is adjacent pin16, unconnected in this section. This was an analyst reading error, not a board defect. Source USART2 RX PA3 and schematic agree; no rewiring or pin reassignment is justified.

Exact flashed ELF disassembly contains USART2_IRQHandler at0x080127E0. It checks RXNE at peripheral0x40004400, calls USART_ReceiveData, then SBUS_Reveive at0x0800E744. Source search found no USART2 pin remapping. USART2_Connect_BT is compiled to do nothing with ENABLE_SBUS=1. Existing100000/8E2 configuration and board hardware inverter remain consistent with SBUS. This proves compiled path presence, not live interrupts or electrical signal quality.

Current receiver cable output-port label and transmitter serial Output Mode remain unknown. The Yahboom-side SBUS connection alone does not identify the receiver-side port. Official FlySky manual distinguishes SERVO serial output from PWM channel/SENS connections and serial S.BUS from i-BUS. Do not change modes or cables based on inference.

## Read-only diagnostic prepared

1. With transmitter OFF, owner observes and reports the label of the receiver socket actually occupied by the cable; ideally provides clear photographs including polarity markings. Do not unplug anything. Wait for confirmation.
2. Separate explicit permission required to switch transmitter ON for menu inspection. Then view Output Mode → Serial without changing it; report selection and LED. Wait for confirmation. This is not a channel-capture retry.
3. If i-BUS or a wrong output port is confirmed, propose a narrowly scoped correction for separate approval. Do not flash or rewire speculatively.
4. If SERVO/S.BUS and physical orientation are verified yet frames remain absent, separately approved passive signal measurement can compare receiver output with inverter output/PA3. Existing telemetry cannot expose raw byte count, RXNE count, UART parity/framing/overrun errors or rejected frame counts. Adding such counters requires new reviewed firmware and separate flash authorization; no counters were fabricated from the saved logs.

Most useful hypothesis to test is serial output configuration/port, now that radio association is supported and the apparent pin mismatch is resolved. Exact root cause remains unverified. Keep actuators isolated and FlySky direct drive disabled. No new B4 session approved or performed here.

References: https://www.flysky-cn.com/ia10b-canshu ; https://www.flysky-cn.com/i6s-xiazai ; https://www.yahboom.net/study/ROS-Driver-Board/5929/ . Enlarged inspection derived from existing work/swd-reference/schematic.png, no new hardware photograph.
