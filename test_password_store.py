"""
test_password_store.py - Unit tests for password_store.py.

Run from the repo root:
    python -m unittest test_password_store -v
"""

import json
import os
import tempfile
import unittest

import password_store


class PasswordStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "users.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_correct_password_accepted(self):
        password_store.add_user("alice", "s3cret!", self.path)
        self.assertTrue(password_store.check_login("alice", "s3cret!", self.path))

    def test_wrong_password_rejected(self):
        password_store.add_user("alice", "s3cret!", self.path)
        self.assertFalse(password_store.check_login("alice", "wrong", self.path))

    def test_unknown_user_rejected(self):
        password_store.add_user("alice", "s3cret!", self.path)
        self.assertFalse(password_store.check_login("mallory", "s3cret!", self.path))

    def test_missing_file_rejects_everyone(self):
        self.assertFalse(password_store.check_login("alice", "x", self.path))

    def test_plaintext_password_not_stored(self):
        password_store.add_user("alice", "s3cret!", self.path)
        with open(self.path, "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("s3cret!", raw)
        record = json.loads(raw)["alice"]
        self.assertEqual(set(record), {"salt", "hash"})

    def test_same_password_gets_different_salt_and_hash(self):
        password_store.add_user("alice", "samepass", self.path)
        password_store.add_user("bob", "samepass", self.path)
        users = password_store.load_users(self.path)
        self.assertNotEqual(users["alice"]["salt"], users["bob"]["salt"])
        self.assertNotEqual(users["alice"]["hash"], users["bob"]["hash"])

    def test_empty_values_refused(self):
        with self.assertRaises(ValueError):
            password_store.add_user("", "pw", self.path)
        with self.assertRaises(ValueError):
            password_store.add_user("alice", "", self.path)


if __name__ == "__main__":
    unittest.main()
