#!/usr/bin/env bash
# OFFLINE compile check of vendor 3.6.5 and the ATLAS patch with arm-none-eabi-gcc.
# This is NOT the vendor toolchain (Keil ARMCC 5.06u7); a GCC image is a different binary and is not
# proposed for flashing without its own stationary regression. Requires: fetch_vendor.sh run first,
# arm-none-eabi-gcc, git, network access to github.com (FreeRTOS GCC port, ST CMSIS startup).
set -Eeuo pipefail
cd "$(dirname "$0")"
W=build_gcc; rm -rf "$W"; mkdir -p "$W/gcc"
unzip -q vendor_dl/ROS-Driver-Board-FW-master.zip -d "$W/x"
cp -r "$W/x/ros-driver-board-fw" "$W/pristine"; cp -r "$W/x/ros-driver-board-fw" "$W/patched"
git -C "$W/patched" init -q && git -C "$W/patched" apply --whitespace=nowarn "$PWD/atlas_rc_report.patch"
git -c advice.detachedHead=false clone -q --depth 1 --branch V10.4.3-LTS-Patch-1 https://github.com/FreeRTOS/FreeRTOS-Kernel "$W/freertos"
git -c advice.detachedHead=false clone -q --depth 1 https://github.com/STMicroelectronics/cmsis_device_f1 "$W/cmsis_f1"
cp "$W/freertos/portable/GCC/ARM_CM3/port.c" "$W/freertos/portable/GCC/ARM_CM3/portmacro.h" "$W/gcc/"
sed 's/\bSVC_Handler\b/vPortSVCHandler/; s/\bPendSV_Handler\b/xPortPendSVHandler/; s/\bSysTick_Handler\b/xPortSysTickHandler/' \
  "$W/cmsis_f1/Source/Templates/gcc/startup_stm32f103xe.s" > "$W/gcc/startup.s"
sed -E 's/(FLASH \(rx\) +: ORIGIN = 0x08000000, LENGTH = )512K/\1256K/; s/(RAM \(xrw\) +: ORIGIN = 0x20000000, LENGTH = )64K/\148K/; s/_estack = 0x2000FFFF;/_estack = 0x2000C000;/' \
  "$W/cmsis_f1/Source/Templates/gcc/linker/STM32F103XE_FLASH.ld" > "$W/gcc/stm32f103rc.ld"
cp gcc/syscalls.c "$W/gcc/"; cp srcs.txt Makefile.gcc "$W/"
(cd "$W" && make -s -j8 -f Makefile.gcc SRC=pristine && make -s -j8 -f Makefile.gcc SRC=patched)
python3 - "$W" <<'PY'
import subprocess, sys, re
w = sys.argv[1]
def calls(elf, fn):
    d = subprocess.run(['arm-none-eabi-objdump', '-d', '--no-show-raw-insn', elf], capture_output=True, text=True).stdout
    m = re.search(r'<%s>:\n(.*?)\n\n' % fn, d, re.S)
    return sorted(set(re.findall(r'\tb(?:l|\.w)?\s+[0-9a-f]+ <([A-Za-z_0-9]+)>', m.group(1)))) if m else None
motion = {'Ackerman_Ctrl', 'Ackerman_Steering', 'Ackerman_A1_Ctrl', 'Ackerman_A1_Steering', 'Mecanum_Ctrl',
          'Fourwheel_Ctrl', 'Motion_Stop', 'Motion_Set_Speed', 'Motor_Set_Pwm'}
for tag in ('pristine', 'patched'):
    c = calls('%s/build/%s/fw.elf' % (w, tag), 'SBUS_Handle')
    print(tag, 'SBUS_Handle calls:', c)
c = calls('%s/build/patched/fw.elf' % w, 'SBUS_Handle')
assert c is not None and not (set(c) & motion), 'patched SBUS_Handle still reaches motion code'
r = calls('%s/build/patched/fw.elf' % w, 'SBUS_Send_Report')
assert r is not None and not (set(r) & motion), r
print('OK: patched image has no SBUS -> motion call path')
PY
