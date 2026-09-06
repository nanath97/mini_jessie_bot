"""Best-effort, bounded post-persistence notification. No Stripe/Airtable API."""
import json
import logging
import os
import threading
import urllib.request
from urllib.parse import urlsplit

_slots = threading.BoundedSemaphore(4)
_log = logging.getLogger('facturx')


def _deliver(response, seller_slug):
    try:
        payload = response.json()
        fields = payload.get('fields')
        if not isinstance(fields, dict) or fields.get('Status') != 'Paid' or not fields.get('Invoice Number'):
            raise ValueError('Persisted response lacks paid invoice fields')
        token = os.getenv('FACTURX_SERVICE_TOKEN', '')
        url = os.getenv('FACTURX_BRIDGE_URL', '').rstrip('/')
        parsed = urlsplit(url)
        if len(token) < 32 or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Invalid Factur-X service configuration')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('FACTURX_BRIDGE_URL requires HTTPS or loopback HTTP')
        request = urllib.request.Request(url + '/internal/facturx/payment',
            data=json.dumps({'paymentFields': fields, 'sellerSlug': seller_slug}).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}, method='POST')
        # Never forward service credentials to redirect targets.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as result:
            if result.status != 202:
                raise ValueError('Bridge did not accept Factur-X job')
            job = json.loads(result.read(4096))
            if not isinstance(job.get('id'), str):
                raise ValueError('Missing Factur-X job identifier')
            _log.info('Factur-X job accepted: %s', job['id'])
    except Exception as exc:
        # Do not log headers, payloads, URLs or arbitrary response bodies.
        _log.error('Factur-X post-persist notification failed (%s)', type(exc).__name__)
    finally:
        _slots.release()


def enqueue_persisted_response(response, seller_slug):
    """Returns immediately. All failure paths preserve the caller's success."""
    acquired = False
    try:
        if os.getenv('FACTURX_ENABLED') != 'true':
            return
        if response.status_code not in (200, 201) or not seller_slug:
            return
        acquired = _slots.acquire(blocking=False)
        if not acquired:
            _log.error('Factur-X post-persist queue full')
            return
        threading.Thread(target=_deliver, args=(response, seller_slug), daemon=True,
                         name='facturx-postpersist').start()
    except Exception:
        if acquired:
            _slots.release()
        _log.error('Factur-X post-persist scheduling failed')
