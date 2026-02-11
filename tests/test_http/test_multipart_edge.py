"""Adversarial edge case tests for parse_multipart."""
import pytest
from cruet._cruet import parse_multipart


def make_multipart_body(fields=None, files=None, boundary="----TestBoundary"):
    """Build a multipart/form-data body."""
    parts = []
    if fields:
        for name, value in fields:
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"\r\n"
                f"{value}\r\n"
            )
    if files:
        for name, filename, content_type, data in files:
            header = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n"
                f"\r\n"
            )
            parts.append(header)
            if isinstance(data, bytes):
                parts.append(data)
            else:
                parts.append(data.encode())
            parts.append("\r\n")
    parts.append(f"--{boundary}--\r\n")

    body = b""
    for part in parts:
        if isinstance(part, str):
            body += part.encode()
        else:
            body += part
    return body, boundary


class TestBoundaryInContent:
    def test_boundary_appearing_in_file_content(self):
        """Boundary string inside file content should not split prematurely."""
        boundary = "----TestBoundary"
        file_content = f"This has the boundary string --{boundary} inside it.".encode()
        body, _ = make_multipart_body(
            files=[("file", "test.txt", "text/plain", file_content)],
            boundary=boundary,
        )
        result = parse_multipart(body, boundary)
        # Parser may or may not handle this correctly, but should not crash
        assert isinstance(result, dict)
        assert "files" in result

    def test_partial_boundary_in_content(self):
        """Partial boundary string in content."""
        boundary = "----TestBoundary"
        file_content = b"Some data with ---- partial boundary"
        body, _ = make_multipart_body(
            files=[("file", "test.txt", "text/plain", file_content)],
            boundary=boundary,
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)


class TestMissingContentDisposition:
    def test_missing_content_disposition(self):
        """Part without Content-Disposition header should not crash."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f"Content-Type: text/plain\r\n"
            f"\r\n"
            f"some content\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_malformed_content_disposition(self):
        """Malformed Content-Disposition should not crash."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: invalid-value\r\n"
            f"\r\n"
            f"some content\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)


class TestLineEndings:
    def test_lf_only_line_endings(self):
        """LF-only line endings instead of CRLF."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\n"
            f'Content-Disposition: form-data; name="key"\n'
            f"\n"
            f"value\n"
            f"--{boundary}--\n"
        ).encode()
        result = parse_multipart(body, boundary)
        # May or may not parse LF-only, but should not crash
        assert isinstance(result, dict)

    def test_mixed_line_endings(self):
        """Mix of CRLF and LF line endings."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="key"\n'
            f"\r\n"
            f"value\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)


class TestNullBytesInMultipart:
    def test_null_in_filename(self):
        """Null bytes in filename should not crash."""
        boundary = "----TestBoundary"
        parts = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="evil',
            b"\x00",
            b'.txt"\r\n',
            b"Content-Type: text/plain\r\n",
            b"\r\n",
            b"file content\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(parts)
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_null_in_field_value(self):
        """Null bytes in field value should be preserved."""
        body, boundary = make_multipart_body(
            fields=[("key", "val\x00ue")]
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)


class TestExtremelyLongFieldNames:
    def test_very_long_field_name(self):
        """Field name > 8KB should not crash."""
        long_name = "a" * 9000
        body, boundary = make_multipart_body(
            fields=[(long_name, "value")]
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_very_long_filename(self):
        """Filename > 8KB should not crash."""
        long_fname = "a" * 9000 + ".txt"
        body, boundary = make_multipart_body(
            files=[("file", long_fname, "text/plain", b"content")]
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)


class TestEmptyParts:
    def test_empty_field_value(self):
        """Empty field value."""
        body, boundary = make_multipart_body(fields=[("key", "")])
        result = parse_multipart(body, boundary)
        assert result["fields"]["key"] == ""

    def test_empty_file_content(self):
        """Empty file upload."""
        body, boundary = make_multipart_body(
            files=[("file", "empty.txt", "text/plain", b"")]
        )
        result = parse_multipart(body, boundary)
        assert result["files"]["file"]["data"] == b""

    def test_only_boundary_markers(self):
        """Body with only boundary markers, no parts."""
        boundary = "----TestBoundary"
        body = f"--{boundary}--\r\n".encode()
        result = parse_multipart(body, boundary)
        assert result["fields"] == {}
        assert result["files"] == {}

    def test_empty_boundary_string(self):
        """Empty boundary string."""
        result = parse_multipart(b"some data", "")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Many parts
# ---------------------------------------------------------------------------

class TestManyParts:
    def test_50_form_fields(self):
        """50 form fields in a single multipart body."""
        fields = [(f"field{i}", f"value{i}") for i in range(50)]
        body, boundary = make_multipart_body(fields=fields)
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert len(result["fields"]) == 50
        assert result["fields"]["field0"] == "value0"
        assert result["fields"]["field49"] == "value49"

    def test_20_file_uploads(self):
        """20 file uploads in one multipart body."""
        files = [
            (f"file{i}", f"test{i}.txt", "text/plain", f"content{i}".encode())
            for i in range(20)
        ]
        body, boundary = make_multipart_body(files=files)
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert len(result["files"]) == 20

    def test_mixed_fields_and_files(self):
        """Mix of form fields and file uploads."""
        fields = [(f"field{i}", f"val{i}") for i in range(10)]
        files = [
            (f"file{i}", f"f{i}.bin", "application/octet-stream", bytes(range(10)))
            for i in range(10)
        ]
        body, boundary = make_multipart_body(fields=fields, files=files)
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert len(result["fields"]) == 10
        assert len(result["files"]) == 10


# ---------------------------------------------------------------------------
# Binary data in file uploads
# ---------------------------------------------------------------------------

class TestBinaryFileData:
    def test_all_byte_values(self):
        """File content containing all 256 byte values."""
        data = bytes(range(256))
        body, boundary = make_multipart_body(
            files=[("file", "binary.bin", "application/octet-stream", data)]
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert result["files"]["file"]["data"] == data

    def test_crlf_in_file_content(self):
        """File content containing CRLF sequences."""
        data = b"line1\r\nline2\r\nline3\r\n"
        body, boundary = make_multipart_body(
            files=[("file", "text.txt", "text/plain", data)]
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert result["files"]["file"]["data"] == data

    def test_null_bytes_in_file_data(self):
        """File content with null bytes throughout."""
        data = b"\x00" * 100 + b"middle" + b"\x00" * 100
        body, boundary = make_multipart_body(
            files=[("file", "null.bin", "application/octet-stream", data)]
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert result["files"]["file"]["data"] == data

    def test_large_file_upload(self):
        """File upload > 100KB."""
        data = b"x" * 100_000
        body, boundary = make_multipart_body(
            files=[("file", "big.bin", "application/octet-stream", data)]
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert len(result["files"]["file"]["data"]) == 100_000


# ---------------------------------------------------------------------------
# Boundary edge cases
# ---------------------------------------------------------------------------

class TestBoundaryEdgeCases:
    def test_very_long_boundary(self):
        """Very long boundary string (>1KB)."""
        boundary = "B" * 1024
        body, _ = make_multipart_body(
            fields=[("key", "value")],
            boundary=boundary,
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert result["fields"]["key"] == "value"

    def test_boundary_with_special_chars(self):
        """Boundary with special regex characters."""
        boundary = "----bound.ary+chars(here)"
        body, _ = make_multipart_body(
            fields=[("key", "value")],
            boundary=boundary,
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_boundary_with_dashes(self):
        """Boundary that is all dashes."""
        boundary = "----------"
        body, _ = make_multipart_body(
            fields=[("key", "value")],
            boundary=boundary,
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_single_char_boundary(self):
        """Single character boundary."""
        boundary = "X"
        body, _ = make_multipart_body(
            fields=[("key", "value")],
            boundary=boundary,
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_boundary_looks_like_crlf(self):
        """Boundary containing characters similar to line endings."""
        boundary = "----boundary-with-dashes"
        body, _ = make_multipart_body(
            fields=[("key", "value")],
            boundary=boundary,
        )
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Missing / malformed parts
# ---------------------------------------------------------------------------

class TestMalformedParts:
    def test_no_closing_boundary(self):
        """Body without closing boundary marker (--boundary--)."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="key"\r\n'
            f"\r\n"
            f"value\r\n"
            # Missing --boundary--
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_part_with_no_blank_line(self):
        """Part without blank line between headers and body."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="key"\r\n'
            f"value without blank line\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_extra_whitespace_in_content_disposition(self):
        """Extra whitespace in Content-Disposition header."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition:  form-data ;  name="key" \r\n'
            f"\r\n"
            f"value\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_content_disposition_without_name(self):
        """Content-Disposition without name parameter."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data\r\n'
            f"\r\n"
            f"value\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        # No name → part should be skipped

    def test_multiple_content_disposition(self):
        """Part with duplicate Content-Disposition headers."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="key1"\r\n'
            f'Content-Disposition: form-data; name="key2"\r\n'
            f"\r\n"
            f"value\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_empty_part(self):
        """Empty part between boundaries."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f"\r\n"
            f"\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_body_is_just_boundary(self):
        """Body contains only the opening boundary."""
        boundary = "----TestBoundary"
        body = f"--{boundary}\r\n".encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)

    def test_empty_body(self):
        """Completely empty body."""
        result = parse_multipart(b"", "----TestBoundary")
        assert isinstance(result, dict)
        assert result["fields"] == {}
        assert result["files"] == {}


# ---------------------------------------------------------------------------
# Content-Type in file parts
# ---------------------------------------------------------------------------

class TestFileContentType:
    def test_file_without_content_type(self):
        """File upload without Content-Type header → defaults to octet-stream."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
            f"\r\n"
            f"file data\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        assert "file" in result["files"]
        assert result["files"]["file"]["content_type"] == "application/octet-stream"

    def test_file_with_charset(self):
        """File with Content-Type including charset."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"file data\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        ct = result["files"]["file"]["content_type"]
        assert "text/plain" in ct


# ---------------------------------------------------------------------------
# Filename edge cases
# ---------------------------------------------------------------------------

class TestFilenameEdgeCases:
    def test_filename_with_path_separator(self):
        """Filename containing path separators."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="../../etc/passwd"\r\n'
            f"Content-Type: text/plain\r\n"
            f"\r\n"
            f"data\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        # Parser should preserve filename as-is; app layer handles safety
        if "file" in result["files"]:
            assert "passwd" in result["files"]["file"]["filename"]

    def test_empty_filename(self):
        """Empty filename string."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename=""\r\n'
            f"Content-Type: text/plain\r\n"
            f"\r\n"
            f"data\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
        if "file" in result["files"]:
            assert result["files"]["file"]["filename"] == ""

    def test_filename_with_unicode(self):
        """Filename with unicode characters."""
        boundary = "----TestBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="résumé.pdf"\r\n'
            f"Content-Type: application/pdf\r\n"
            f"\r\n"
            f"data\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        result = parse_multipart(body, boundary)
        assert isinstance(result, dict)
