"""
Runtime patch for twikit's x_client_transaction.

Twikit 2.3.3 (latest on PyPI, unmaintained since ~2025-04) ships a broken
extractor for X's `ondemand.s` bundle hash. X changed its home-page JS format
so the single-step regex in twikit's `ClientTransaction.get_indices` no longer
matches, producing: Exception("Couldn't get KEY_BYTE indices").

The upstream standalone library (iSarabjitDhiman/XClientTransaction, commit
47bb8d6, 2026-03-18) replaced that with a two-step lookup. This module ports
that fix back into twikit's async code path by monkey-patching
`ClientTransaction.get_indices` at import time.
"""
import re

from twikit.x_client_transaction import transaction as _tx

_ON_DEMAND_INDEX_REGEX = re.compile(r""",(\d+):["']ondemand\.s["']""")
_ON_DEMAND_HASH_TEMPLATE = r',{}:"([0-9a-f]+)"'


async def _patched_get_indices(self, home_page_response, session, headers):
    key_byte_indices = []
    response = self.validate_response(home_page_response) or self.home_page_response
    home_html = str(response)

    index_match = _ON_DEMAND_INDEX_REGEX.search(home_html)
    if index_match:
        hash_match = re.search(
            _ON_DEMAND_HASH_TEMPLATE.format(index_match.group(1)), home_html
        )
        if hash_match:
            filename = hash_match.group(1)
            on_demand_file_url = (
                f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{filename}a.js"
            )
            on_demand_file_response = await session.request(
                method="GET", url=on_demand_file_url, headers=headers
            )
            for item in _tx.INDICES_REGEX.finditer(str(on_demand_file_response.text)):
                key_byte_indices.append(item.group(2))

    if not key_byte_indices:
        raise Exception("Couldn't get KEY_BYTE indices")
    key_byte_indices = list(map(int, key_byte_indices))
    return key_byte_indices[0], key_byte_indices[1:]


_tx.ClientTransaction.get_indices = _patched_get_indices
