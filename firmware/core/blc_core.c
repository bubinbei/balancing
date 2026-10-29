#include "blc_core.h"
#include <limits.h>
#include <string.h>

static void put16(uint8_t *out, uint16_t value) {
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8);
}

static void put32(uint8_t *out, uint32_t value) {
    unsigned i;
    for (i = 0; i < 4; ++i) out[i] = (uint8_t)(value >> (8u * i));
}

static void put64(uint8_t *out, uint64_t value) {
    unsigned i;
    for (i = 0; i < 8; ++i) out[i] = (uint8_t)(value >> (8u * i));
}

void blc_queue_init(blc_queue *queue) {
    memset(queue, 0, sizeof(*queue));
}

int blc_queue_push_locked(blc_queue *queue, const blc_event *event) {
    if (queue->count == BLC_CAPTURE_SLOTS) {
        if (queue->known_dropped < UINT32_MAX) ++queue->known_dropped;
        if (queue->known_dropped == UINT32_MAX) queue->counter_saturated = 1;
        return 0;
    }
    queue->events[queue->head] = *event;
    queue->head = (uint16_t)((queue->head + 1u) % BLC_CAPTURE_SLOTS);
    ++queue->count;
    if (queue->count > queue->high_water) queue->high_water = queue->count;
    return 1;
}

int blc_queue_pop_locked(blc_queue *queue, blc_event *event) {
    if (!queue->count) return 0;
    *event = queue->events[queue->tail];
    queue->tail = (uint16_t)((queue->tail + 1u) % BLC_CAPTURE_SLOTS);
    --queue->count;
    return 1;
}

void blc_clock_begin_epoch(blc_clock *clock, uint32_t epoch) {
    clock->anchor_us = 0;
    clock->epoch = epoch;
    clock->uncertain = 0;
}

int blc_clock_extend(blc_clock *clock, uint32_t captured,
                     uint64_t silence_age_us, uint64_t *timestamp_us) {
    uint32_t difference = captured - (uint32_t)clock->anchor_us;
    int64_t delta = difference <= INT32_MAX ? (int64_t)difference
                    : (int64_t)difference - INT64_C(4294967296);
    uint64_t candidate;
    if (clock->uncertain || difference == UINT32_C(2147483648)
        || silence_age_us >= UINT64_C(2147483648)) {
        clock->uncertain = 1;
        return 0;
    }
    if (delta < 0) {
        uint64_t backward = (uint64_t)(-delta);
        if (backward > clock->anchor_us) { clock->uncertain = 1; return 0; }
        candidate = clock->anchor_us - backward;
    } else {
        if (UINT64_MAX - clock->anchor_us < (uint64_t)delta) { clock->uncertain = 1; return 0; }
        candidate = clock->anchor_us + (uint64_t)delta;
    }
    if (candidate > clock->anchor_us) clock->anchor_us = candidate;
    *timestamp_us = candidate;
    return 1;
}

uint32_t blc_crc32(const uint8_t *bytes, size_t size) {
    uint32_t crc = UINT32_MAX;
    size_t i;
    for (i = 0; i < size; ++i) {
        unsigned bit;
        crc ^= bytes[i];
        for (bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xEDB88320) : 0u);
    }
    return crc ^ UINT32_MAX;
}

size_t blc_encode_frame(uint8_t kind, uint16_t flags, uint32_t sequence,
                       uint64_t base_us, const uint8_t *payload, uint16_t payload_size,
                       uint8_t *output, size_t capacity) {
    size_t total = (size_t)payload_size + 28u;
    if (payload_size > BLC_MAX_PAYLOAD || (flags & ~1u) || capacity < total || !output
        || (payload_size && !payload)) return 0;
    memcpy(output, "BLC1", 4);
    output[4] = 1;
    output[5] = kind;
    put16(output + 6, flags);
    put16(output + 8, payload_size);
    put16(output + 10, 0);
    put32(output + 12, sequence);
    put64(output + 16, base_us);
    if (payload_size) memcpy(output + 24, payload, payload_size);
    put32(output + 24 + payload_size, blc_crc32(output, (size_t)payload_size + 24u));
    return total;
}

void blc_encode_sample(uint8_t output[28], uint8_t sensor, uint8_t mask,
                       uint16_t quality, uint32_t sequence, uint64_t capture_us,
                       const int16_t counts[6]) {
    unsigned i;
    output[0] = sensor;
    output[1] = mask;
    put16(output + 2, quality);
    put32(output + 4, sequence);
    put64(output + 8, capture_us);
    for (i = 0; i < 6; ++i) put16(output + 16 + 2u * i, (uint16_t)counts[i]);
}

void blc_decode_le16_xyz(const uint8_t bytes[6], int16_t counts[3]) {
    unsigned i;
    for (i = 0; i < 3; ++i) {
        uint32_t word = (uint32_t)bytes[2u * i] | ((uint32_t)bytes[2u * i + 1u] << 8);
        int32_t signed_word = word >= 32768u ? (int32_t)word - 65536 : (int32_t)word;
        counts[i] = (int16_t)signed_word;
    }
}

void blc_decode_lis3dh_hr_xyz(const uint8_t bytes[6], int16_t counts[3]) {
    unsigned i;
    for (i = 0; i < 3; ++i) {
        uint32_t word = ((uint32_t)bytes[2u * i] | ((uint32_t)bytes[2u * i + 1u] << 8)) >> 4;
        int32_t signed_word = word >= 2048u ? (int32_t)word - 4096 : (int32_t)word;
        counts[i] = (int16_t)signed_word;
    }
}
