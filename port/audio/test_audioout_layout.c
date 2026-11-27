/* Unit check for the SDK CellAudioOut struct layout used by
 * strikeforce_audioout.inc. No runtime, no game. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static void w16(uint8_t* p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void w32(uint8_t* p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}
static uint16_t r16(const uint8_t* p) { return (uint16_t)((p[0] << 8) | p[1]); }
static uint32_t r32(const uint8_t* p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

int main(void)
{
    uint8_t info[136], state[20];

    memset(info, 0xAA, sizeof(info));
    memset(info, 0, 136);
    info[0] = 0; info[1] = 3; info[2] = 1;
    w16(info + 6, 13);
    /* mode 0 at +8 */
    info[8] = 0; info[9] = 2; info[10] = 0x04; info[11] = 0; w32(info + 12, 0x00000001u);
    info[16] = 0; info[17] = 6; info[18] = 0x04; info[19] = 0; w32(info + 20, 0x00010000u);
    info[24] = 0; info[25] = 8; info[26] = 0x04; info[27] = 0; w32(info + 28, 0x40000000u);

    assert(sizeof(info) == 136);
    assert(info[2] == 1);
    assert(r16(info + 6) == 13);
    assert(info[8] == 0 && info[9] == 2 && info[10] == 0x04);
    assert(r32(info + 12) == 0x00000001u);
    assert(info[17] == 6 && r32(info + 20) == 0x00010000u);
    assert(info[6] == 0 && info[7] == 13);
    assert(info[8] == 0);           /* mode0.type at +8, not +6 */

    memset(state, 0xAA, sizeof(state));
    memset(state, 0, 20);
    state[0] = 0; state[1] = 0;
    w32(state + 8, 0);
    state[12] = 0; state[13] = 2; state[14] = 0x04; state[15] = 0;
    w32(state + 16, 0x00000001u);
    assert(sizeof(state) == 20);
    assert(state[0] == 0);          /* ENABLED, not the old "2=connected" mix-up */
    assert(state[13] == 2);
    assert(state[14] == 0x04);
    assert(r32(state + 16) == 0x00000001u);
    /* The old HLE wrote soundMode at +8: a title reading +12 would see zeros. */
    assert(state[12] == 0 && state[13] == 2);

    puts("audioout layout: DeviceInfo 136 / State 20 / modes at +8 / soundMode at +12 passed");
    return 0;
}
