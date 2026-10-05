"""Bounded, TLS-verified Bitrix requests without credential-bearing diagnostics."""

import json
import http.client
import ssl
import time
import urllib.error
import urllib.request

from bitrix_config import ToolError

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
READ_METHODS = {"tasks.task.get", "tasks.task.list", "im.dialog.messages.get"}
WRITE_METHODS = {"tasks.task.add", "tasks.task.update", "tasks.task.complete",
                 "tasks.task.chat.message.send", "im.message.add"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, config, *, transport=None, sleep=time.sleep):
        self.config = config
        self.sleep = sleep
        if transport is None:
            try:
                context = ssl.create_default_context(cafile=config.ca_bundle)
            except (OSError, ssl.SSLError):
                raise ToolError("TLS_CONFIG", "Cannot load the configured CA certificate bundle.") from None
            transport = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=context), NoRedirect()).open
        self.transport = transport

    def call(self, method, payload, *, write=False, v3=False):
        if method not in (WRITE_METHODS if write else READ_METHODS):
            raise ToolError("METHOD_NOT_ALLOWED", "Method is outside this tool's declared capabilities.")
        cfg = self.config
        url = f"{cfg.portal}/rest/{'api/' if v3 else ''}{cfg.webhook_user_id}/{cfg.token}/{method}"
        request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        attempts = 1 if write else cfg.read_retries + 1
        for attempt in range(attempts):
            try:
                with self.transport(request, timeout=cfg.timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ToolError("INVALID_RESPONSE", "Response exceeded the size limit.", uncertain=write)
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise ToolError("INVALID_RESPONSE", "API did not return valid JSON.", uncertain=write) from None
                if not isinstance(body, dict):
                    raise ToolError("INVALID_RESPONSE", "API response must be an object.", uncertain=write)
                if "error" in body:
                    rate_limited = body.get("error") in ("QUERY_LIMIT_EXCEEDED", "OPERATION_TIME_LIMIT")
                    if not write and rate_limited and attempt + 1 < attempts:
                        self.sleep(min(2 ** attempt, 4))
                        continue
                    # Do not echo API descriptions: they may contain portal URLs or request bodies.
                    raise ToolError("API_REJECTED", "Bitrix rejected the request.", retryable=not write and rate_limited)
                if "result" not in body or body["result"] is None or body["result"] is False:
                    raise ToolError("INVALID_RESPONSE", "API did not confirm a result.", uncertain=write)
                return body
            except urllib.error.HTTPError as exc:
                transient = exc.code == 429 or exc.code >= 500
                if not write and transient and attempt + 1 < attempts:
                    self.sleep(min(2 ** attempt, 4))
                    continue
                raise ToolError("HTTP_ERROR", "API returned an HTTP error.",
                                uncertain=write and (exc.code >= 500 or 300 <= exc.code < 400),
                                retryable=not write and transient) from None
            except (urllib.error.URLError, TimeoutError, OSError, ssl.SSLError, http.client.HTTPException):
                if not write and attempt + 1 < attempts:
                    self.sleep(min(2 ** attempt, 4))
                    continue
                raise ToolError("TRANSPORT_ERROR", "Request failed; check connectivity and trusted certificates.",
                                uncertain=write, retryable=not write) from None
        raise AssertionError("Unreachable retry state")
