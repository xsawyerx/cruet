#include "percent_encode.h"
#include "buffer.h"
#include <stdlib.h>
#include <ctype.h>

static int
hex_digit(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

size_t
cruet_percent_decode(char *str, size_t len)
{
    size_t r = 0, w = 0;
    while (r < len) {
        if (str[r] == '%' && r + 2 < len) {
            int hi = hex_digit(str[r + 1]);
            int lo = hex_digit(str[r + 2]);
            if (hi >= 0 && lo >= 0) {
                str[w++] = (char)((hi << 4) | lo);
                r += 3;
                continue;
            }
        }
        if (str[r] == '+') {
            str[w++] = ' ';
            r++;
        } else {
            str[w++] = str[r++];
        }
    }
    str[w] = '\0';
    return w;
}

static int
needs_encode(unsigned char c)
{
    if (isalnum(c)) return 0;
    if (c == '-' || c == '_' || c == '.' || c == '~') return 0;
    return 1;
}

char *
cruet_percent_encode(const char *str, size_t len, size_t *out_len)
{
    static const char hex[] = "0123456789ABCDEF";
    Cruet_Buffer buf;
    cruet_buf_init(&buf);

    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)str[i];
        if (needs_encode(c)) {
            cruet_buf_append_char(&buf, '%');
            cruet_buf_append_char(&buf, hex[c >> 4]);
            cruet_buf_append_char(&buf, hex[c & 0xf]);
        } else {
            cruet_buf_append_char(&buf, (char)c);
        }
    }
    cruet_buf_append_char(&buf, '\0');

    if (out_len)
        *out_len = buf.len - 1; /* exclude null terminator */
    return buf.data; /* caller frees */
}
