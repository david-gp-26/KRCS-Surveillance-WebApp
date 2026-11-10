"""Voice note -> text, through the speech-to-text service (POST /transcribe, AI/ML §6.3, §7.2).

Does not import frappe: the client is built in jobs.make_context. The conversation falls back to asking the
reporter to type when the service is off, fails, or isn't confident.
"""

import requests


class TranscriptionClient:
	def __init__(self, url, token=None, timeout=45):
		self.url = url.rstrip("/") + "/transcribe"
		self.headers = {"Accept": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
		self.timeout = timeout

	def transcribe(self, audio, mime_type=None, language=None):
		"""The text, or None when the service isn't confident in it. No retry: a voice note is slow to process and
		the reporter is waiting."""
		r = requests.post(
			self.url,
			data=audio,
			params={"language": language} if language else None,
			headers={**self.headers, "Content-Type": mime_type or "application/octet-stream"},
			timeout=self.timeout,
		)
		r.raise_for_status()
		body = r.json()
		return body.get("text") if body.get("usable") else None
