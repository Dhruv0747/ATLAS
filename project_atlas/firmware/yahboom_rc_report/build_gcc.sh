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
git -C "$W/patched" init -q && git -C "$W/patched" apply --whitespace=nowarn "$PWD/atlas_rc_report.patch" "$PWD/atlas_gcc_compat.patch"
git -c advice.detachedHead=false clone -q --depth 1 --branch V10.4.3-LTS-Patch-1 https://github.com/FreeRTOS/FreeRTOS-Kernel "$W/freertos"
git -c advice.detachedHead=false clone -q --depth 1 https://github.com/STMicroelectronics/cmsis_device_f1 "$W/cmsis_f1"
cp "$W/freertos/portable/GCC/ARM_CM3/port.c" "$W/freertos/portable/GCC/ARM_CM3/portmacro.h" "$W/gcc/"
sed 's/\bSVC_Handler\b/vPortSVCHandler/; s/\bPendSV_Handler\b/xPortPendSVHandler/; s/\bSysTick_Handler\b/xPortSysTickHandler/' \
  "$W/cmsis_f1/Source/Templates/gcc/startup_stm32f103xe.s" > "$W/gcc/startup.s"
sed -E 's/(FLASH \(rx\) +: ORIGIN = 0x08000000, LENGTH = )512K/\1256K/; s/(RAM \(xrw\) +: ORIGIN = 0x20000000, LENGTH = )64K/\148K/; s/_estack = 0x2000FFFF;/_estack = 0x2000C000;/' \
  "$W/cmsis_f1/Source/Templates/gcc/linker/STM32F103XE_FLASH.ld" > "$W/gcc/stm32f103rc.ld"
cp gcc/syscalls.c "$W/gcc/"; cp srcs.txt Makefile.gcc "$W/"
(cd "$W" && make -s -j8 -f Makefile.gcc SRC=pristine && make -s -j8 -f Makefile.gcc SRC=patched)
python3 -I audit_gcc_image.py "$W/build/patched/fw.elf" vendor_dl/rosmaster_V3.6.5.hex "$W/patched/Source/APP/app.c"
