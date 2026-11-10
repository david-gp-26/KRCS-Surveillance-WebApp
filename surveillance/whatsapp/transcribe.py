"""Voice note -> text, through the speech-to-text service (POST /transcribe, AI/ML §6.3, §7.2).

The same service, URL and token (site config `stt_url`, `stt_token`) as surveillance.transcription, which
transcribes voice notes in the background for officers; the audio goes as the form field `file`, as it does there.
Does not import frappe: the client is built in jobs.make_context. The conversation falls back to asking the
reporter to type when the service is off, fails, or isn't confident.
"""

import requests


class TranscriptionClient:
	def __init__(self, url, token=None, timeout=45):
		self.url = url.rstrip("/") + "/transcribe"
		self.headers = {"Accept": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
		self.timeout = timeout

	def transcribe(self, audio, mime_type=None, filename=None):
		"""{"text", "language"}, or None when the service isn't confident in it. No retry: a voice note is slow to
		process and the reporter is waiting. A service that gives no `usable` verdict is trusted when it has text."""
		r = requests.post(
			self.url,
			files={"file": (filename or "voice-note", audio, mime_type or "application/octet-stream")},
			headers=self.headers,
			timeout=self.timeout,
		)
		r.raise_for_status()
		body = r.json()
		text = (body.get("text") or "").strip()
		if not text or not body.get("usable", True):
			return None
		return {"text": text, "language": body.get("language")}
