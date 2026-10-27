#!/usr/bin/env bash
# OFFLINE compile check of vendor 3.6.5 and the ATLAS patch with arm-none-eabi-gcc.
# This is NOT the vendor toolchain (Keil ARMCC 5.06u7); a GCC image is a different binary and is not
# proposed for flashing without its own stationary regression. Requires: fetch_vendor.sh run first,
# arm-none-eabi-gcc, git, network access to github.com (FreeRTOS GCC port, ST CMSIS startup).
set -Eeuo pipefail
export SOURCE_DATE_EPOCH=1793077129
export TZ=UTC
export LC_ALL=C
cd "$(dirname "$0")"
printf '%s  %s\n' 3d7a6e1c762bdd42dad81468cd34d6907847ab8ebb03abb16024d888a4f0687e vendor_dl/ROS-Driver-Board-FW-master.zip 088af51933e98e51105412a0dbf4f5d078dbc3bcff7664105a094d073e12b55b vendor_dl/rosmaster_V3.6.5.hex | sha256sum -c -
W=build_gcc; rm -rf "$W"; mkdir -p "$W/gcc"
unzip -q vendor_dl/ROS-Driver-Board-FW-master.zip -d "$W/x"
cp -r "$W/x/ros-driver-board-fw" "$W/pristine"; cp -r "$W/x/ros-driver-board-fw" "$W/patched"
git -C "$W/patched" init -q && git -C "$W/patched" apply --whitespace=nowarn "$PWD/atlas_rc_report.patch" "$PWD/atlas_gcc_compat.patch"
git -c advice.detachedHead=false clone -q --depth 1 --branch V10.4.3-LTS-Patch-1 https://github.com/FreeRTOS/FreeRTOS-Kernel "$W/freertos"
git init -q "$W/cmsis_f1"
git -C "$W/cmsis_f1" fetch -q --depth 1 https://github.com/STMicroelectronics/cmsis_device_f1 c8e9a4a4f16b6d2cb2a2083cbe5161025280fb22
git -C "$W/cmsis_f1" checkout -q --detach FETCH_HEAD
test "$(git -C "$W/freertos" rev-parse HEAD)" = 628059b775ba7e0e5d7492291035c6f7c9870be5
test "$(git -C "$W/cmsis_f1" rev-parse HEAD)" = c8e9a4a4f16b6d2cb2a2083cbe5161025280fb22
cp "$W/freertos/portable/GCC/ARM_CM3/port.c" "$W/freertos/portable/GCC/ARM_CM3/portmacro.h" "$W/gcc/"
sed 's/\bSVC_Handler\b/vPortSVCHandler/; s/\bPendSV_Handler\b/xPortPendSVHandler/; s/\bSysTick_Handler\b/xPortSysTickHandler/' \
  "$W/cmsis_f1/Source/Templates/gcc/startup_stm32f103xe.s" > "$W/gcc/startup.s"
sed -E 's/(FLASH \(rx\) +: ORIGIN = 0x08000000, LENGTH = )512K/\1256K/; s/(RAM \(xrw\) +: ORIGIN = 0x20000000, LENGTH = )64K/\148K/; s/_estack = 0x2000FFFF;/_estack = 0x2000C000;/' \
  "$W/cmsis_f1/Source/Templates/gcc/linker/STM32F103XE_FLASH.ld" > "$W/gcc/stm32f103rc.ld"
cp gcc/syscalls.c "$W/gcc/"; cp srcs.txt Makefile.gcc "$W/"
(cd "$W" && make -s -j8 -f Makefile.gcc SRC=pristine && make -s -j8 -f Makefile.gcc SRC=patched)
python3 -I audit_gcc_image.py "$W/build/patched/fw.elf" vendor_dl/rosmaster_V3.6.5.hex "$W/patched/Source/APP/app.c"

arm-none-eabi-objcopy -O binary "$W/build/patched/fw.elf" "$W/build/patched/fw.bin"
