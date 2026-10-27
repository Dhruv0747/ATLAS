#!/usr/bin/env python3
"""Offline audit of a GCC-built ROS-Driver-Board image against the vendor Keil release hex.

Checks (exit 1 on any failure):
  0. The image ends below the settings sector (sector 120, 0x0803C000) so a page-erase flash keeps it.
  1. Interrupt vectors: the set of vector slots with a real handler equals the vendor image's set
     (vendor: every unused slot shares one Default_Handler address; fault handlers are B . loops in both).
  2. No interrupt handler can reach a FreeRTOS API (all ATLAS-relevant IRQs run above
     configMAX_SYSCALL_INTERRUPT_PRIORITY, so such a call would break the kernel's rules).
  3. SBUS_Handle and SBUS_Send_Report have no call path to motion/motor/steering code.
  4. Conservative static stack depth per FreeRTOS task (direct calls only, ~64 B context) fits the task
     stack sizes found in app.c. Indirect calls are not followed; this is an estimate, not a proof.
Usage: audit_gcc_image.py <fw.elf> <vendor.hex> <app.c>
"""
import collections
import functools
import re
import subprocess
import sys

VECTORS = ['_estack', 'Reset', 'NMI', 'HardFault', 'MemManage', 'BusFault', 'UsageFault', 'r7', 'r8', 'r9', 'r10',
           'SVC', 'DebugMon', 'r13', 'PendSV', 'SysTick', 'WWDG', 'PVD', 'TAMPER', 'RTC', 'FLASH', 'RCC', 'EXTI0',
           'EXTI1', 'EXTI2', 'EXTI3', 'EXTI4', 'DMA1_Ch1', 'DMA1_Ch2', 'DMA1_Ch3', 'DMA1_Ch4', 'DMA1_Ch5',
           'DMA1_Ch6', 'DMA1_Ch7', 'ADC1_2', 'USB_HP_CAN1_TX', 'USB_LP_CAN1_RX0', 'CAN1_RX1', 'CAN1_SCE',
           'EXTI9_5', 'TIM1_BRK', 'TIM1_UP', 'TIM1_TRG_COM', 'TIM1_CC', 'TIM2', 'TIM3', 'TIM4', 'I2C1_EV',
           'I2C1_ER', 'I2C2_EV', 'I2C2_ER', 'SPI1', 'SPI2', 'USART1', 'USART2', 'USART3', 'EXTI15_10',
           'RTCAlarm', 'USBWakeUp', 'TIM8_BRK', 'TIM8_UP', 'TIM8_TRG_COM', 'TIM8_CC', 'ADC3', 'FSMC', 'SDIO',
           'TIM5', 'SPI3', 'UART4', 'UART5', 'TIM6', 'TIM7', 'DMA2_Ch1', 'DMA2_Ch2', 'DMA2_Ch3', 'DMA2_Ch4_5']
CORE_FAULTS = {'NMI', 'HardFault', 'MemManage', 'BusFault', 'UsageFault', 'DebugMon'}
MOTION = re.compile(r'^(Ackerman_\w+|Mecanum_\w+|Fourwheel_\w+|Motion_(Stop|Set_Speed|Set_Pwm|Ctrl\w*)|Motor_\w+|'
                    r'PwmServo_Set\w*|TIM_SetCompare\w*)$')
RTOS = re.compile(r'^(x|v|ux|pv|ul)(Task|Queue|Port|Timer|EventGroup|Semaphore|List)|Critical')


def hex_words(path, n):
    data = {}
    base = 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        count, addr, typ = b[0], (b[1] << 8) | b[2], b[3]
        if typ == 4:
            base = ((b[4] << 8) | b[5]) << 16
        elif typ == 0:
            for i in range(count):
                data[base + addr + i] = b[4 + i]
    return [int.from_bytes(bytes(data.get(0x08000000 + 4 * i + k, 0) for k in range(4)), 'little') for i in range(n)]


def implemented(vec):
    default = collections.Counter(vec[16:]).most_common(1)[0][0]
    return {VECTORS[i] for i in range(1, len(VECTORS))
            if vec[i] and vec[i] != default and not re.fullmatch(r'r\d+', VECTORS[i])}


def callgraph(elf):
    d = subprocess.run(['arm-none-eabi-objdump', '-d', '--no-show-raw-insn', elf], capture_output=True,
                       text=True, check=True).stdout
    g, frame, cur, n = {}, {}, None, 0
    for line in d.splitlines():
        m = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
        if m:
            cur, n = m.group(1), 0
            g[cur], frame[cur] = set(), 0
            continue
        if not cur:
            continue
        n += 1
        if n <= 8:
            m = re.search(r'\t(?:push(?:\.w)?|stmdb\s+sp!,)\s*\{([^}]*)\}', line)
            if m:
                frame[cur] += 4 * len([r for r in m.group(1).split(',') if r.strip()])
            m = re.search(r'\tsub(?:\.w|w)?\s+sp,\s*(?:sp,\s*)?#(\d+)', line)
            if m:
                frame[cur] += int(m.group(1))
        m = re.search(r'\tb(?:l|\.w|\.n)?\s+[0-9a-f]+ <([A-Za-z_][A-Za-z_0-9]*)>', line)
        if m and m.group(1) != cur:
            g[cur].add(m.group(1))
    return g, frame


def main(elf, vendor_hex, app_c):
    ok = True
    gcc_vec = implemented(hex_words(_to_hex(elf), len(VECTORS)))
    ven_vec = implemented(hex_words(vendor_hex, len(VECTORS)))
    diff = (ven_vec - CORE_FAULTS) ^ gcc_vec - {'_estack'}
    print('vectors vendor:', sorted(ven_vec))
    print('vectors gcc   :', sorted(gcc_vec))
    if diff:
        ok = False
        print('FAIL vector mismatch:', sorted(diff))
    else:
        print('OK   vector set identical (vendor core-fault B . stubs == GCC Default_Handler loop)')

    end = max(a for a in _hex_addrs(_to_hex(elf)))
    if end >= 0x0803C000:
        ok = False
        print('FAIL image ends at 0x%08X, overlapping the settings sector 120 (0x0803C000)' % end)
    else:
        print('OK   image ends at 0x%08X, below settings sector 120 (0x0803C000, kept by page erase)' % end)

    g, frame = callgraph(elf)

    def reach(fn, seen=None):
        seen = set() if seen is None else seen
        for c in g.get(fn, ()):
            if c not in seen:
                seen.add(c)
                reach(c, seen)
        return seen

    for v in sorted(gcc_vec - {'Reset', 'SVC', 'PendSV', 'SysTick'}):
        handler = v + ('_IRQHandler' if not v.endswith('Handler') else '')
        bad = sorted(x for x in reach(handler) if RTOS.search(x))
        if bad:
            ok = False
            print('FAIL %s reaches FreeRTOS: %s' % (handler, bad))
        else:
            print('OK   %s: no FreeRTOS call' % handler)

    for fn in ('SBUS_Handle', 'SBUS_Send_Report', 'SBUS_Reveive'):
        bad = sorted(x for x in reach(fn) | set(g.get(fn, ())) if MOTION.match(x))
        if fn not in g or bad:
            ok = False
            print('FAIL %s motion path: %s' % (fn, bad or 'function missing'))
        else:
            print('OK   %s: no motion/motor/steering path' % fn)

    @functools.lru_cache(None)
    def depth(fn, stack=()):
        if fn in stack or len(stack) > 30:
            return 0, ()
        best = (0, ())
        for c in g.get(fn, ()):
            r = depth(c, stack + (fn,))
            if r[0] > best[0]:
                best = r
        return frame.get(fn, 0) + best[0], (fn,) + best[1]

    src = open(app_c, encoding='utf-8', errors='replace').read()
    for task, words in re.findall(r'xTaskCreate\((\w+),\s*"[^"]*",\s*(\d+)', src):
        need, path = depth(task)
        size = int(words) * 4
        verdict = 'OK  ' if need + 64 <= size else 'FAIL'
        ok &= verdict == 'OK  '
        print('%s stack %-18s %5d B, static worst %4d B + 64 ctx  (%s)' % (verdict, task, size, need,
                                                                         '>'.join(path[:6])))
    return 0 if ok else 1


def _hex_addrs(path):
    base = 0
    for line in open(path):
        b = bytes.fromhex(line.strip()[1:])
        if b[3] == 4:
            base = ((b[4] << 8) | b[5]) << 16
        elif b[3] == 0:
            yield base + ((b[1] << 8) | b[2]) + b[0] - 1


def _to_hex(elf):
    out = elf + '.audit.hex'
    subprocess.run(['arm-none-eabi-objcopy', '-O', 'ihex', elf, out], check=True)
    return out


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
