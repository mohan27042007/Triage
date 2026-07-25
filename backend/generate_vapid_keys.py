"""Print a VAPID key pair for Railway Web Push configuration.

Run locally once. Store the output only in Railway variables; do not commit it
or add it to a local .env file tracked by Git.
"""

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def main() -> None:
    vapid = Vapid()
    vapid.generate_keys()
    private_key = vapid.private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_key = vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    print(f"VAPID_PUBLIC_KEY={_base64url(public_key)}")
    print(f"VAPID_PRIVATE_KEY={_base64url(private_key)}")


if __name__ == "__main__":
    main()
