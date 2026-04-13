"""AES-GCM decryption and M-Bus frame extraction for the EVN/Sagemcom T210-D."""

import logging
from binascii import unhexlify
from typing import Tuple

from Cryptodome.Cipher import AES

logger = logging.getLogger(__name__)

# Fixed read size for Sagemcom T210-D M-Bus frames (bytes)
FRAME_SIZE = 282


def validate_mbus_start(data_hex: str) -> bool:
    """Return True if the hex string starts with a valid M-Bus frame header.

    The header is: 0x68 [len] [len] 0x68 (bytes 0-3).
    """
    if len(data_hex) < 8:
        return False
    return (
        data_hex[0:2] == "68"
        and data_hex[2:4] == data_hex[4:6]  # length byte repeated
        and data_hex[6:8] == "68"
    )


def extract_frame_parts(data_hex: str) -> Tuple[str, str, str]:
    """Extract (system_title, frame_counter, encrypted_frame) from raw hex data.

    Byte offsets (each byte = 2 hex chars):
      byte  1    : frame length
      bytes 11-18: system title (8 bytes)
      bytes 22-25: frame counter (4 bytes)
      bytes 26+  : encrypted APDU payload
    """
    frame_len = int(data_hex[2:4], 16)
    system_title = data_hex[22:38]
    frame_counter = data_hex[44:52]
    frame = data_hex[52: 12 + frame_len * 2]
    return system_title, frame_counter, frame


def evn_decrypt(frame_hex: str, key_hex: str, system_title_hex: str, frame_counter_hex: str) -> str:
    """Decrypt an AES-128-GCM encrypted M-Bus frame.

    Returns the decrypted payload as a hex string.
    Raises ValueError / binascii.Error if inputs are malformed.
    """
    frame = unhexlify(frame_hex)
    key = unhexlify(key_hex)
    iv = unhexlify(system_title_hex + frame_counter_hex)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    return cipher.decrypt(frame).hex()
