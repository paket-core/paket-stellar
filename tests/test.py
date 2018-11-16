"""Tests for paket module."""
import unittest

import paket_stellar


def setup_account(new_account=False, xlm_starting_balance=50000000, trust_bul=False):
    """Generate new keypair, and optionally create account and set trust."""
    keypair = paket_stellar.get_keypair()

    if new_account:
        create_account_transaction = paket_stellar.prepare_create_account(
            paket_stellar.ISSUER, keypair.address().decode(), xlm_starting_balance)
        paket_stellar.submit_transaction_envelope(create_account_transaction, paket_stellar.ISSUER_SEED)

    if new_account and trust_bul:
        trust_transaction = paket_stellar.prepare_trust(keypair.address().decode())
        paket_stellar.submit_transaction_envelope(trust_transaction, keypair.seed().decode())

    return keypair


# pylint: disable=too-many-instance-attributes
class BasePaketTest(unittest.TestCase):
    """Base class for all paket tests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.invalid_seed = 'invalid seed string'
        self.invalid_pubkey = 'invalid pubkey string'

        bul_account_keypair = setup_account(new_account=True, trust_bul=True)
        self.bul_account_seed = bul_account_keypair.seed().decode()
        self.bul_account_pubkey = bul_account_keypair.address().decode()

        regular_account_keypair = setup_account(new_account=True, xlm_starting_balance=100000000)
        self.regular_account_seed = regular_account_keypair.seed().decode()
        self.regular_account_pubkey = regular_account_keypair.address().decode()

        keypair = setup_account()
        self.seed = keypair.seed().decode()
        self.address = keypair.address().decode()
# pylint: enable=too-many-instance-attributes



class TestGetKeypair(BasePaketTest):
    """Tests for get_keypair function."""

    def test_get_from_seed(self):
        """Test for getting keypair from seed."""
        keypair = paket_stellar.get_keypair(seed=self.seed)
        self.assertEqual(keypair.address().decode(), self.address)

    def test_get_from_pubkey(self):
        """Test for getting keypair from pubkey."""
        keypair = paket_stellar.get_keypair(pubkey=self.address)
        self.assertIsNone(keypair.signing_key)

    def test_get_random(self):
        """Test for getting random keypair."""
        keypair = paket_stellar.get_keypair()
        self.assertIsNotNone(keypair.signing_key)
        self.assertIsNotNone(keypair.address())

    def test_get_from_invalid_seed(self):
        """Test for getting keypair from invalid seed."""
        with self.assertRaises(paket_stellar.stellar_base.exceptions.DecodeError):
            paket_stellar.get_keypair(seed=self.invalid_seed)

    def test_get_from_invalid_pubkey(self):
        """Test for getting from invalid pubkey."""
        with self.assertRaises(paket_stellar.stellar_base.exceptions.DecodeError):
            paket_stellar.get_keypair(pubkey=self.invalid_pubkey)


class TestGetBulAccount(BasePaketTest):
    """Tests for get_bul_account function."""

    def test_get_bul_account(self):
        """Test for getting bul account."""
        account = paket_stellar.get_bul_account(pubkey=self.bul_account_pubkey)
        self.assertIn('bul_balance', account)

    def test_accept_untrusted(self):
        """Test for getting bul account that actualy may not have bul balance."""
        account = paket_stellar.get_bul_account(self.regular_account_pubkey, accept_untrusted=True)
        self.assertNotIn('bul_balance', account)
        with self.assertRaises(paket_stellar.TrustError):
            paket_stellar.get_bul_account(self.regular_account_pubkey)


class TestAddMemo(BasePaketTest):
    """Tests for adding memo."""

    def test_long_memo(self):
        """Test for adding memo with length greater than 28 bytes."""
        memo = 'This is very long text that will be truncated to 28 bytes length'
        builder = paket_stellar.stellar_base.builder.Builder(secret=self.regular_account_seed)
        builder = paket_stellar.add_memo(builder, memo)
        memo_length = len(builder.memo.text)
        self.assertGreater(memo_length, 0)
        self.assertLessEqual(memo_length, 28)

    def test_short_memo(self):
        """Test for adding memo with length less or equal than 28 bytes."""
        memo = 'This is short text of 28 len'
        builder = paket_stellar.stellar_base.builder.Builder(secret=self.regular_account_seed)
        builder = paket_stellar.add_memo(builder, memo)
        self.assertEqual(builder.memo.text, memo.encode('utf-8'))


class TestSubmit(BasePaketTest):
    """Tests for submit function."""

    def test_submit(self):
        """Test submitting properly created and signed transaction."""
        new_keypair = paket_stellar.get_keypair()
        pubkey = new_keypair.address().decode()
        create_account_transaction = paket_stellar.prepare_create_account(
            self.regular_account_pubkey, pubkey, 50000000)
        result = paket_stellar.submit_transaction_envelope(create_account_transaction, self.regular_account_seed)
        self.assertIn('result_xdr', result)
        self.assertEqual(result['result_xdr'], 'AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAA=')

    def test_submit_anauth(self):
        """Test submitting unsigned transaction."""
        new_keypair = paket_stellar.get_keypair()
        pubkey = new_keypair.address().decode()
        builder = paket_stellar.gen_builder(pubkey=self.regular_account_pubkey)
        builder.append_create_account_op(destination=pubkey, starting_balance=5)
        with self.assertRaises(paket_stellar.StellarTransactionFailed):
            paket_stellar.submit(builder)


class TestRelay(BasePaketTest):
    """Test for relay transactions."""

    def test_create_relay(self):
        """Test creating relay transactions."""

        relay_keypair = setup_account(new_account=True, trust_bul=True)
        relayer_keypair = paket_stellar.get_keypair()
        relayee_keypair = paket_stellar.get_keypair()

        relay_details = paket_stellar.prepare_relay(
            relay_keypair.address().decode(), relayer_keypair.address().decode(),
            relayee_keypair.address().decode(), 100000000, 150000000, 1568455600)

        self.assertTrue(
            relay_details['set_options_transaction'] and
            relay_details['relay_transaction'] and
            relay_details['sequence_merge_transaction'] and
            relay_details['timelock_merge_transaction'])
