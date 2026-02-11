#ifndef CRUET_BUFFER_H
#define CRUET_BUFFER_H

#include <stddef.h>
#include <string.h>

/* Simple growable byte buffer. */
typedef struct {
    char *data;
    size_t len;
    size_t cap;
} Cruet_Buffer;

static inline void cruet_buf_init(Cruet_Buffer *buf) {
    buf->data = NULL;
    buf->len = 0;
    buf->cap = 0;
}

int cruet_buf_grow(Cruet_Buffer *buf, size_t need);
int cruet_buf_append(Cruet_Buffer *buf, const char *data, size_t len);
int cruet_buf_append_char(Cruet_Buffer *buf, char c);
void cruet_buf_free(Cruet_Buffer *buf);

#endif
