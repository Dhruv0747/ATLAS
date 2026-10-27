# B4 NO SBUS — saved-evidence investigation only

Owner confirmed transmitter OFF. No serial connection, hardware operation, settings change, service restart or retry performed.

## Verified

Saved corrected B4:2033 RC reports,seq0,ever=false,drive_disabled=true; no accepted SBUS frame. CH1–10 are unavailable. No byte/error/rejected-frame counters exist in this report, so absence of UART bytes cannot be distinguished from rejected input. Healthy USART1 USB telemetry does not prove USART2 works.

Reviewed exact built patched source: ENABLE_USART2=1, ENABLE_SBUS=1; USART2_BAUDRATE100000. RX PA3 floating input, TX PA2 alternate push-pull. STM32 word length9 with even parity provides8 data bits,2 stop bits,no flow control. RXNE interrupt enabled; USART2_IRQHandler reads the byte and calls SBUS_Reveive. The report sequence/ever flags increment only after25 bytes with0x0F header and0x00 footer. A different footer, framing/polarity mismatch or absent signal can all leave ever=false. Existing ISR waits for RXNE and does not expose parity/framing/overrun counters; no runtime interrupt diagnosis can be claimed from this recording.

Saved manufacturer schematic image work/swd-reference/schematic.png, YB-ERF01-V3.0, shows SBUS U4 pin1 signal,pin2 5V,pin3 GND. Q1 SS8050 and pull-up R2 form the inverter to RXD2. **Documentation inconsistency:** MCU schematic labels RXD2 on PA2 while firmware configures PA3 as USART2 RX. It is not established whether the schematic labeling is erroneous or the user's PCB differs. Do not infer actual continuity or instruct wiring changes without verification. Physical connector viewing orientation also cannot be inferred from schematic numbering alone.

Official FlySky FS-iA10B specification supports PWM/PPM/i-BUS/S.BUS: https://www.flysky-cn.com/ia10b-canshu . Official FS-i6S manual section7.5 distinguishes Output PWM/PPM from Serial i-BUS/S.BUS and identifies SERVO as serial output: https://www.flyskytech.com/u_file/photo/20210420/FS-i6S%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E%E4%B9%A620210416.pdf . Yahboom describes S/V/G and USART2 RX: https://www.yahboom.net/study/ROS-Driver-Board/5929/ . This establishes expected configuration, not current selected mode or actual wiring.

## Unknown / hypotheses

Current receiver port label, connector orientation, pairing/LED observation, selected transmitter serial mode and electrical signal remain unknown. Owner answered only transmitter OFF to the observation question. No particular failure is proven most likely statistically. Output mode or wrong output-port selection is the first low-risk hypothesis to check; wiring/polarity, schematic discrepancy and decoder/interrupt issues remain open. No firmware correction is justified yet.

## Sequential diagnostic plan

1. Keep transmitter OFF and every actuator disconnected. Obtain a clear photograph of the receiver cable/labels and Yahboom SBUS connector/silkscreen without touching wiring; owner confirms completion before continuing. Ask what LED was observed during the completed ON test, if remembered. Do not interpret current OFF-link LED as proof of past binding.
2. After separate permission to power transmitter ON, inspect Output Mode without changing it and observe receiver LED/binding indication. Record the screen and exact receiver model/manual before interpreting LED patterns. No capture retry or binding action is automatic.
3. If serial mode is i-BUS or cable is on the wrong documented output, propose only that specific correction for approval. Never swap wires or infer supply polarity by cable color. Resolve physical pin orientation first.
4. If settings/binding/wiring are verified, use a separately approved passive logic-analyzer observation at receiver output and board RX path to discriminate absent signal, wrong protocol/polarity and MCU-side rejection. Do not attach instruments while powered without a reviewed safe connection plan.
5. If necessary, prepare separately reviewed UART RX/error/header/footer counters offline; deployment requires separate flash approval. Existing logs cannot supply these missing counters.

Smallest necessary action now: identify receiver port and physical orientation from photographs, with transmitter OFF. No live B4 retry until these observations narrow the cause. Firmware V3.6.161 and working telemetry remain unchanged.
