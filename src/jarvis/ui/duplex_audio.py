"""Local Chromium capture and playback sharing WebRTC's echo-cancellation path."""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from PySide6.QtCore import QObject, QUrl, Signal, Slot


class DuplexAudio(QObject):
    audio = Signal(str, int)
    listening_changed = Signal(bool)
    error = Signal(str)
    played = Signal(int)
    output_level = Signal(float, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.listening = False
        self.active = False
        self.booted = False
        self.page = None
        self.profile = None
        self.server = None
        self.requested = None
        self.url = ""
        self.settings = {}

    def start(self, microphone="", speaker=""):
        self.active = True
        self.requested = (microphone, speaker)
        if self.page is None:
            self._create_page()
        if self.booted:
            self._js("start", microphone, speaker)

    def _create_page(self):
        # Lazy import: ordinary typing and click-to-talk do not load Chromium.
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import (
            QWebEnginePage,
            QWebEnginePermission,
            QWebEngineProfile,
            QWebEngineSettings,
        )
        route = "/" + secrets.token_urlsafe(24)
        html = Path(__file__).with_name("duplex_audio.html").read_bytes()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != route:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(html)
            def log_message(self, format, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        server = self.server
        Thread(target=lambda:server.serve_forever(poll_interval=0.05), daemon=True, name="jarvis-local-audio").start()
        self.url = f"http://127.0.0.1:{self.server.server_port}{route}"
        port = self.server.server_port
        allowed_url = self.url
        class LocalAudioPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
                return url.toString() in {allowed_url, "about:blank"}
        self.profile = QWebEngineProfile(self)
        self.page = LocalAudioPage(self.profile, self)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        channel = QWebChannel(self.page)
        channel.registerObject("audio", self)
        self.page.setWebChannel(channel)
        def permission(request):
            if (self.active and request.permissionType() == QWebEnginePermission.PermissionType.MediaAudioCapture
                    and request.origin().host() == "127.0.0.1" and request.origin().port() == port):
                request.grant()
            else:
                request.deny()
        self.page.permissionRequested.connect(permission)
        self.page.setUrl(QUrl(self.url))

    def _js(self, method, *arguments):
        if self.page is not None and self.booted:
            self.page.runJavaScript("window.jarvisAudio." + method + "(" + ",".join(json.dumps(a) for a in arguments) + ")")

    @Slot(str, int)
    def pcm(self, encoded, rate):
        if self.active and self.listening and 8000 <= rate <= 192000 and len(encoded) <= 8192:
            self.audio.emit(encoded, rate)

    @Slot(str, str)
    def notify(self, kind, value):
        if kind == "boot":
            self.booted = True
            if self.active and self.requested:
                self._js("start", *self.requested)
        elif kind == "listening" and self.active:
            self.settings = json.loads(value)
            self.listening = True
            self.listening_changed.emit(True)
        elif kind == "played":
            self.played.emit(int(value))
        elif kind == "error":
            self.stop()
            self.error.emit(value[:350])

    @Slot(float, int)
    def meter(self, level, epoch):
        if self.active and self.listening and 0 <= level <= 1:
            self.output_level.emit(level, epoch)

    def push(self, encoded, epoch):
        self._js("push", encoded, epoch)

    def finish(self, epoch):
        self._js("finish", epoch)

    def silence(self, epoch):
        self._js("stopAudio", epoch)

    def duck(self, enabled):
        self._js("duck", enabled)

    def stop(self):
        self.active = self.listening = False
        self._js("stopMic")
        self.listening_changed.emit(False)

    def shutdown(self):
        self.stop()
        if self.page is not None:
            profile = self.profile
            if profile is not None:
                profile.setParent(None)
                self.page.destroyed.connect(profile.deleteLater)
                self.profile = None
            self.page.setAudioMuted(True)
            self.page.setUrl(QUrl("about:blank"))
            self.page.deleteLater()
            self.page = None
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
