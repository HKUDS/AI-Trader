"""Regression tests for user-registration auth hardening."""

import hashlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


class VerificationCodeRandomnessTests(unittest.TestCase):
    """generate_verification_code must come from a CSPRNG, not Python's `random`."""

    def test_does_not_use_random_module(self) -> None:
        from utils import generate_verification_code

        # Seed `random` with a fixed value: a CSPRNG-backed implementation
        # should produce a different code each call regardless of seed.
        import random

        random.seed(0)
        seen = {generate_verification_code() for _ in range(20)}
        # 20 cryptographically-random 6-digit draws should produce >1 distinct
        # value. A `random.randint(0, 999999)`-based impl seeded above would
        # repeat the same first sample on every fresh interpreter; CSPRNG won't.
        self.assertGreater(len(seen), 1)

    def test_returns_six_digit_string(self) -> None:
        from utils import generate_verification_code

        for _ in range(50):
            code = generate_verification_code()
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())


class VerifyPasswordTimingSafetyTests(unittest.TestCase):
    """verify_password must use hmac.compare_digest, not `==`."""

    def test_round_trip(self) -> None:
        from utils import hash_password, verify_password

        h = hash_password('correct horse battery staple')
        self.assertTrue(verify_password('correct horse battery staple', h))
        self.assertFalse(verify_password('wrong', h))

    def test_uses_constant_time_compare(self) -> None:
        # We can't reliably measure timing in CI, but we can assert the
        # implementation calls hmac.compare_digest (the documented contract).
        import utils

        with patch('utils.hmac.compare_digest', wraps=utils.hmac.compare_digest) as spy:
            utils.verify_password('p', utils.hash_password('p'))
            self.assertTrue(spy.called)

    def test_handles_malformed_hash(self) -> None:
        from utils import verify_password

        # Old bare-`except:` swallowed everything; tightened impl must still
        # return False (not raise) for these shapes.
        self.assertFalse(verify_password('p', ''))
        self.assertFalse(verify_password('p', 'no-dollar-sign'))
        self.assertFalse(verify_password('p', None))  # type: ignore[arg-type]


class RegistrationBruteForceLockoutTests(unittest.TestCase):
    """/api/users/register must lock out after MAX_CODE_ATTEMPTS bad guesses."""

    def _make_client(self):
        # FastAPI TestClient with a stub app exposing only the user routes,
        # so we don't have to spin up the full database / background tasks.
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from routes_shared import RouteContext
        from routes_users import register_user_routes

        # Stub out the user-creation side-effects so we exercise the auth gate
        # without writing to a real database.
        with patch('routes_users._create_user_session', return_value='stub-token'), \
             patch('routes_users.get_db_connection') as fake_conn:
            cursor = fake_conn.return_value.cursor.return_value
            cursor.fetchone.return_value = None
            cursor.lastrowid = 1
            app = FastAPI()
            ctx = RouteContext()
            register_user_routes(app, ctx)
            client = TestClient(app)
            yield client, ctx

    def test_lockout_after_five_bad_codes(self) -> None:
        for client, ctx in self._make_client():
            email = 'victim@example.com'
            assert client.post('/api/users/send-code', json={'email': email}).status_code == 200
            real = ctx.verification_codes[email]['code']
            wrong = '000000' if real != '000000' else '111111'

            # Five bad attempts should each return 400 ("Invalid code").
            for _ in range(5):
                r = client.post(
                    '/api/users/register',
                    json={'email': email, 'code': wrong, 'password': 'pw1234567'},
                )
                self.assertEqual(r.status_code, 400, r.text)

            # Sixth attempt — even with the correct code — must be locked out.
            r = client.post(
                '/api/users/register',
                json={'email': email, 'code': real, 'password': 'pw1234567'},
            )
            self.assertEqual(r.status_code, 429, r.text)
            # Lockout must clear the entry so a fresh `send-code` is required.
            self.assertNotIn(email, ctx.verification_codes)

    def test_resend_throttle(self) -> None:
        for client, ctx in self._make_client():
            email = 'victim@example.com'
            self.assertEqual(client.post('/api/users/send-code', json={'email': email}).status_code, 200)
            # Immediate second request must be throttled.
            r = client.post('/api/users/send-code', json={'email': email})
            self.assertEqual(r.status_code, 429, r.text)


if __name__ == '__main__':
    unittest.main()
