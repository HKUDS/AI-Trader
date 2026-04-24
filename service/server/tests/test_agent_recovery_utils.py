import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
except ImportError:  # pragma: no cover - optional in local test environments
    Account = None
    encode_defunct = None

from utils import build_agent_token_recovery_challenge, recover_signed_address, validate_address


@unittest.skipIf(Account is None, 'eth_account not installed')
class AgentRecoveryUtilsTests(unittest.TestCase):
    def test_recover_signed_address_returns_signer(self) -> None:
        account = Account.create()
        wallet_address = validate_address(account.address)
        challenge = build_agent_token_recovery_challenge(
            agent_id=1768,
            agent_name='SoraTrader2',
            wallet_address=wallet_address,
            nonce='demo-nonce',
            expires_at='2026-04-21T06:00:00Z',
        )
        signed = Account.sign_message(encode_defunct(text=challenge), private_key=account.key)

        recovered = recover_signed_address(challenge, signed.signature.hex())

        self.assertEqual(recovered, wallet_address)

    def test_recover_signed_address_rejects_tampered_message(self) -> None:
        account = Account.create()
        wallet_address = validate_address(account.address)
        challenge = build_agent_token_recovery_challenge(
            agent_id=1768,
            agent_name='SoraTrader2',
            wallet_address=wallet_address,
            nonce='demo-nonce',
            expires_at='2026-04-21T06:00:00Z',
        )
        signed = Account.sign_message(encode_defunct(text=challenge), private_key=account.key)

        recovered = recover_signed_address(f'{challenge}\nTampered: true', signed.signature.hex())

        self.assertNotEqual(recovered, wallet_address)


if __name__ == '__main__':
    unittest.main()
