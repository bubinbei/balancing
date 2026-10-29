#include "blc_core.h"
#include <stdio.h>
#include <string.h>

/* Do not use assert(): Release builds must execute every check. */
#define CHECK(value) do { if (!(value)) { fprintf(stderr, "failed line %d: %s\n", __LINE__, #value); return 1; } } while (0)

int main(int argc, char **argv) {
    blc_queue queue;
    blc_clock clock;
    blc_event event = {0}, result;
    uint8_t encoded[BLC_MAX_FRAME], payload[44] = {0};
    int16_t counts[6] = {INT16_MIN, -1, 0, 1, INT16_MAX, -1234};
    int16_t decoded[3];
    const uint8_t le16[6] = {0, 128, 255, 255, 255, 127};
    const uint8_t hr12[6] = {0, 128, 240, 255, 240, 127};
    uint64_t time;
    unsigned i;
    size_t length;
    CHECK(blc_crc32((const uint8_t *)"123456789", 9) == UINT32_C(0xCBF43926));
    CHECK(blc_crc32(NULL, 0) == 0);
    blc_decode_le16_xyz(le16, decoded);
    CHECK(decoded[0] == INT16_MIN && decoded[1] == -1 && decoded[2] == INT16_MAX);
    blc_decode_lis3dh_hr_xyz(hr12, decoded);
    CHECK(decoded[0] == -2048 && decoded[1] == -1 && decoded[2] == 2047);
    blc_queue_init(&queue);
    for (i = 0; i < BLC_CAPTURE_SLOTS; ++i) {
        event.sequence = i;
        CHECK(blc_queue_push_locked(&queue, &event));
    }
    CHECK(!blc_queue_push_locked(&queue, &event));
    CHECK(queue.known_dropped == 1 && queue.high_water == 256);
    for (i = 0; i < BLC_CAPTURE_SLOTS; ++i) {
        CHECK(blc_queue_pop_locked(&queue, &result));
        CHECK(result.sequence == i);
    }
    CHECK(!blc_queue_pop_locked(&queue, &result));
    queue.known_dropped = UINT32_MAX - 1u;
    queue.count = BLC_CAPTURE_SLOTS;
    CHECK(!blc_queue_push_locked(&queue, &event) && queue.counter_saturated);
    blc_clock_begin_epoch(&clock, 1);
    CHECK(blc_clock_extend(&clock, 100, 100, &time) && time == 100);
    CHECK(blc_clock_extend(&clock, 90, 0, &time) && time == 90 && clock.anchor_us == 100);
    CHECK(blc_clock_extend(&clock, 0x70000000u, 1000, &time));
    CHECK(blc_clock_extend(&clock, 0xE0000000u, 1000, &time));
    CHECK(blc_clock_extend(&clock, 0xFFFFFFF0u, 1000, &time));
    CHECK(blc_clock_extend(&clock, 16, 32, &time) && time == UINT64_C(4294967312));
    CHECK(!blc_clock_extend(&clock, 32, UINT64_C(2147483648), &time));
    CHECK(!blc_clock_extend(&clock, 33, 1, &time));
    blc_clock_begin_epoch(&clock, 2);
    CHECK(blc_clock_extend(&clock, 20, 20, &time) && time == 20);
    CHECK(!blc_clock_extend(&clock, UINT32_C(2147483668), 1, &time));
    payload[0] = 1; payload[4] = 2; payload[8] = 1; payload[10] = 28;
    blc_encode_sample(payload + 16, 0, 63, 0, 0xFFFFFFFEu, 123456, counts);
    length = blc_encode_frame(3, 1, 8, 123456, payload, 44, encoded, sizeof(encoded));
    CHECK(length == 72);
    CHECK(!blc_encode_frame(3, 1, 8, 0, payload, 44, encoded, 71));
    CHECK(!blc_encode_frame(3, 2, 8, 0, payload, 44, encoded, sizeof(encoded)));
    if (argc == 2 && strcmp(argv[1], "--vector") == 0) {
        for (i = 0; i < length; ++i) printf("%02x", encoded[i]);
        puts("");
    } else puts("portable core: CRC, queue, saturation, rollover, epoch and serialization passed");
    return 0;
}
