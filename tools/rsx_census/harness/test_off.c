/* With RSX_CENSUS unset nothing is recorded and no file is written. */
#include <stdio.h>
#include <string.h>
typedef unsigned int u32;
#include "../census_hook.c"
int main(void)
{
    for (u32 i = 0; i < 100000; i++) { if (s_rsxc_mode) rsx_census_method(0x0A68, i & 1); if (!(i % 100)) rsx_census_frame(); rsx_census_draw(i); }
    FILE* f = fopen("rsx_census_off.txt", "r");
    printf("%s mode=%d\n", (s_rsxc_mode == 0 && !f) ? "OFF PASS" : "OFF FAIL", s_rsxc_mode);
    return (s_rsxc_mode == 0 && !f) ? 0 : 1;
}
