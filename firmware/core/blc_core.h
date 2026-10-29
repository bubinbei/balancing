#ifndef BLC_CORE_H
#define BLC_CORE_H

#include <stddef.h>
#include <stdint.h>

#define BLC_CAPTURE_SLOTS 256u
#define BLC_MAX_PAYLOAD 1024u
#define BLC_MAX_FRAME 1052u

typedef struct {
    uint64_t timestamp_us;
    uint32_t sequence;
    uint16_t flags;
    uint8_t source;
    uint8_t kind;
} blc_event;

typedef struct {
    blc_event events[BLC_CAPTURE_SLOTS];
    uint16_t head, tail, count, high_water;
    uint32_t known_dropped;
    int counter_saturated;
} blc_queue;

/* Caller must hold an ISR-safe, bounded exclusion guard across each operation.
 * These functions are NOT thread-safe by themselves and use no RTOS primitives.
 * The board adapter must measure its critical sections; native tests cannot.
 */
void blc_queue_init(blc_queue *queue);
int blc_queue_push_locked(blc_queue *queue, const blc_event *event);
int blc_queue_pop_locked(blc_queue *queue, blc_event *event);

typedef struct {
    uint64_t anchor_us;
    uint32_t epoch;
    int uncertain;
} blc_clock;

void blc_clock_begin_epoch(blc_clock *clock, uint32_t epoch);
/* silence_age_us comes from an independently supervised coarse clock. It is
 * never exported as the precise event timestamp. >= half-wrap fails closed.
 * Out-of-order nearby captures may precede anchor; anchor never goes backwards.
 */
int blc_clock_extend(blc_clock *clock, uint32_t captured,
                     uint64_t silence_age_us, uint64_t *timestamp_us);

uint32_t blc_crc32(const uint8_t *bytes, size_t size);
size_t blc_encode_frame(uint8_t kind, uint16_t flags, uint32_t sequence,
                       uint64_t base_us, const uint8_t *payload, uint16_t payload_size,
                       uint8_t *output, size_t capacity);
/* Sample fields are serialized explicitly; C struct padding is never wire data. */
void blc_encode_sample(uint8_t output[28], uint8_t sensor, uint8_t mask,
                       uint16_t quality, uint32_t sequence, uint64_t capture_us,
                       const int16_t counts[6]);

void blc_decode_le16_xyz(const uint8_t bytes[6], int16_t counts[3]);
void blc_decode_lis3dh_hr_xyz(const uint8_t bytes[6], int16_t counts[3]);

#endif
