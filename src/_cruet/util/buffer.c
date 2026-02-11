#include "buffer.h"
#include <stdlib.h>

int
cruet_buf_grow(Cruet_Buffer *buf, size_t need)
{
    if (buf->len + need <= buf->cap)
        return 0;
    size_t new_cap = buf->cap ? buf->cap * 2 : 64;
    while (new_cap < buf->len + need)
        new_cap *= 2;
    char *new_data = realloc(buf->data, new_cap);
    if (!new_data)
        return -1;
    buf->data = new_data;
    buf->cap = new_cap;
    return 0;
}

int
cruet_buf_append(Cruet_Buffer *buf, const char *data, size_t len)
{
    if (cruet_buf_grow(buf, len) < 0)
        return -1;
    memcpy(buf->data + buf->len, data, len);
    buf->len += len;
    return 0;
}

int
cruet_buf_append_char(Cruet_Buffer *buf, char c)
{
    return cruet_buf_append(buf, &c, 1);
}

void
cruet_buf_free(Cruet_Buffer *buf)
{
    free(buf->data);
    buf->data = NULL;
    buf->len = 0;
    buf->cap = 0;
}
