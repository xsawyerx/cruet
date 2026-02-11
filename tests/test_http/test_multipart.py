"""Tests for multipart/form-data parser."""
import io
import pytest
from cruet._cruet import parse_multipart


def make_multipart_body(fields=None, files=None, boundary="----TestBoundary"):
    """Build a multipart/form-data body."""
    parts = []
    if fields:
        for name, value in fields:
            parts.append(
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"\r\n"
                f"\r\n"
                f"{value}\r\n"
            )
    if files:
        for name, filename, content_type, data in files:
            header = (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
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


class TestMultipartSingleFile:
    def test_single_file_upload(self):
        body, boundary = make_multipart_body(
            files=[("file", "test.txt", "text/plain", b"hello world")]
        )
        result = parse_multipart(body, boundary)
        assert "file" in result["files"]
        f = result["files"]["file"]
        assert f["filename"] == "test.txt"
        assert f["content_type"] == "text/plain"
        assert f["data"] == b"hello world"


class TestMultipartMixedFieldsFiles:
    def test_fields_and_files(self):
        body, boundary = make_multipart_body(
            fields=[("name", "John"), ("age", "30")],
            files=[("avatar", "photo.jpg", "image/jpeg", b"\xff\xd8\xff\xe0")]
        )
        result = parse_multipart(body, boundary)
        assert result["fields"]["name"] == "John"
        assert result["fields"]["age"] == "30"
        assert "avatar" in result["files"]
        assert result["files"]["avatar"]["filename"] == "photo.jpg"


class TestMultipartMultipleFiles:
    def test_multiple_files(self):
        body, boundary = make_multipart_body(
            files=[
                ("file1", "a.txt", "text/plain", b"aaa"),
                ("file2", "b.txt", "text/plain", b"bbb"),
            ]
        )
        result = parse_multipart(body, boundary)
        assert result["files"]["file1"]["data"] == b"aaa"
        assert result["files"]["file2"]["data"] == b"bbb"


class TestMultipartLargeFile:
    def test_large_file(self):
        data = b"x" * 100_000
        body, boundary = make_multipart_body(
            files=[("big", "big.bin", "application/octet-stream", data)]
        )
        result = parse_multipart(body, boundary)
        assert len(result["files"]["big"]["data"]) == 100_000


class TestMultipartBoundaryEdgeCases:
    def test_custom_boundary(self):
        body, boundary = make_multipart_body(
            fields=[("key", "value")],
            boundary="==customBoundary123=="
        )
        result = parse_multipart(body, boundary)
        assert result["fields"]["key"] == "value"

    def test_boundary_with_dashes(self):
        body, boundary = make_multipart_body(
            fields=[("k", "v")],
            boundary="----WebKitFormBoundaryABC123"
        )
        result = parse_multipart(body, boundary)
        assert result["fields"]["k"] == "v"


class TestMultipartMalformed:
    def test_empty_body(self):
        result = parse_multipart(b"", "boundary")
        assert result["fields"] == {}
        assert result["files"] == {}

    def test_no_final_boundary(self):
        body = (
            b"--boundary\r\n"
            b"Content-Disposition: form-data; name=\"key\"\r\n"
            b"\r\n"
            b"value\r\n"
        )
        result = parse_multipart(body, "boundary")
        assert result["fields"]["key"] == "value"

    def test_fields_only(self):
        body, boundary = make_multipart_body(
            fields=[("a", "1"), ("b", "2"), ("c", "3")]
        )
        result = parse_multipart(body, boundary)
        assert result["fields"] == {"a": "1", "b": "2", "c": "3"}
        assert result["files"] == {}
