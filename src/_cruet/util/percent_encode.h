#ifndef CRUET_PERCENT_ENCODE_H
#define CRUET_PERCENT_ENCODE_H

#include <stddef.h>

/* Decode percent-encoded string in-place. Returns new length. */
size_t cruet_percent_decode(char *str, size_t len);

/* Encode string for URL. Caller must free result. Returns NULL on alloc failure. */
char *cruet_percent_encode(const char *str, size_t len, size_t *out_len);

#endif
