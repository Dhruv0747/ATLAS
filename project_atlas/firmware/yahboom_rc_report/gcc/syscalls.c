/* GCC-only glue: route newlib printf to the vendor's ARMCC-style fputc retarget (USART1). */
#include <stdio.h>
int fputc(int ch, FILE *f);
int _write(int fd, char *p, int n) { for (int i = 0; i < n; i++) fputc(p[i], 0); return n; }
