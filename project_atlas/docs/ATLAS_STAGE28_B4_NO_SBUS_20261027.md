# Corrected B4 session: logging PASS, channel test BLOCKED

One owner-approved session using exact commit eaae8d883753a3cb861a7facca8bd4e7f5973756. Clean source comparison, tool SHA256 evidence,12 native logging tests and present CH340 COM26 verified before capture. Owner confirmed all actuators isolated, transmitter OFF initially, Jetson shut down, stable power and USB. V3.6.161 identity relies on prior B3 boot verification; no reset or active version query was performed.

Numbered snapshots worked and status was checked through the freshness-aware reader. Owner was instructed to turn transmitter ON only after monitoring and drive-disabled status were verified, then confirmed ON with untouched controls. At that check:1813 RC reports received; last5seconds contained122 reports, zero fresh/ever frames, seq0, channels=null, drive_disabled=true. Live refers to board report delivery, not radio-link validity.

Owner instructed to switch transmitter OFF. Capture stopped without retry:83.344seconds,10164 board packets,2033 RC reports, zero serial writes. Terminal snapshot confirms port_closed=true. No logging/checksum/serial exception or nonzero-motion rejection occurred. Raw SHA256247f02cb3a3e358371c2fa47497aba02892efa6807d6c22e0afe7c79472124b3.

CH1–CH10 unavailable, not zero. Direction/range/stability and transmitter-loss behavior NOT TESTED. frame_lost=false/failsafe=false with ever=false does not prove a healthy radio link or functional failsafe. No valid frame ever reached the STM32 reporting path during capture.

The cause is not established: receiver pairing/output mode, connection/electrical format and STM32 receive path remain possible. No wiring or mode changes authorized/performed, no transmitter cycling retry, no reset, flash, motor activation or Jetson deployment. Electrical output levels were not measured; physical isolation remains required.

Private evidence: work/stage28-b4-corrected-20261027 contains raw data, reports, numbered status snapshots, tool hashes, stop marker and SHA256SUMS. Transmitter OFF requested; confirmation pending at report time.

Next necessary step after OFF confirmation: inspect receiver binding indication, exact output-port label and transmitter receiver-output setting without changing them. A new live capture requires separate approval. Do not infer that the firmware or receiver is faulty from absent frames alone.
